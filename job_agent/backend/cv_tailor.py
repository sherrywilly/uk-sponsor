from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document

from .claude_client import ClaudeClient
from .config import BASE_CV_PATH, CV_OUTPUT_DIR, PROFILE


def _safe_stem(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text)[:80]


def _inject_keywords(text: str, keywords: list[str]) -> str:
    missing = [k for k in keywords if k.lower() not in text.lower()]
    if not missing:
        return text
    suffix = " | Keywords: " + ", ".join(missing[:5])
    return text + suffix


def apply_cv_diff(base_doc_path: Path, diff: dict[str, Any], company: str) -> tuple[Path, int]:
    if not base_doc_path.exists():
        raise FileNotFoundError(f"Base CV not found: {base_doc_path}")

    doc = Document(base_doc_path)
    summary_rewrite = diff.get("summary_rewrite")
    keywords = diff.get("keywords_to_inject", [])

    if summary_rewrite and doc.paragraphs:
        doc.paragraphs[0].text = summary_rewrite

    for edit in diff.get("experience_edits", [])[:5]:
        add_bullet = edit.get("add_bullet")
        if add_bullet:
            doc.add_paragraph(f"- {add_bullet}")

    if doc.paragraphs and keywords:
        doc.paragraphs[-1].text = _inject_keywords(doc.paragraphs[-1].text, keywords)

    match_score = int(diff.get("match_score", 0) or 0)
    file_base = f"{_safe_stem(company)}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    out_docx = CV_OUTPUT_DIR / f"{file_base}.docx"
    out_pdf = CV_OUTPUT_DIR / f"{file_base}.pdf"

    doc.save(out_docx)

    libreoffice = shutil.which("libreoffice")
    if libreoffice:
        subprocess.run(
            [libreoffice, "--headless", "--convert-to", "pdf", "--outdir", str(CV_OUTPUT_DIR), str(out_docx)],
            check=False,
            capture_output=True,
            text=True,
        )

    return (out_pdf if out_pdf.exists() else out_docx), match_score


async def tailor_cv(client: ClaudeClient, compressed_jd: dict[str, Any], company: str) -> tuple[str, int]:
    diff = await client.tailor_cv_gap(compressed_jd)
    cv_path, match_score = apply_cv_diff(BASE_CV_PATH, diff, company)

    required = compressed_jd.get("required_skills", [])
    required_text = " ".join(required).lower()
    cv_text = " ".join(p.text for p in Document(cv_path if cv_path.suffix == ".docx" else BASE_CV_PATH).paragraphs).lower()
    if required_text:
        tokens = [w for w in re.findall(r"[a-zA-Z0-9\+#\.]+", required_text) if len(w) > 3]
        if tokens:
            matched = sum(1 for t in set(tokens) if t in cv_text)
            score = int((matched / max(1, len(set(tokens)))) * 100)
            match_score = max(match_score, score)

    if match_score < 80:
        profile_summary = PROFILE.get("summary", "")
        _ = profile_summary

    return str(cv_path), match_score
