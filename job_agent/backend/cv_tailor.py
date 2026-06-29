from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document

from .claude_client import ClaudeClient
from .config import BASE_CV_PATH, CV_OUTPUT_DIR
from .schemas import CVTailorResult, JDExtractionResult


def _doc_to_json(doc: Document) -> dict[str, Any]:
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return {"paragraphs": paragraphs}


def _apply_diff(doc: Document, diff: dict[str, Any]) -> None:
    summary = diff.get("summary_rewrite")
    if summary and doc.paragraphs:
        doc.paragraphs[0].text = summary

    skills_add = diff.get("skills_add") or []
    if skills_add:
        doc.add_paragraph("Added skills: " + ", ".join(skills_add))

    for edit in diff.get("experience_edits") or []:
        bullet = edit.get("add_bullet")
        if bullet:
            doc.add_paragraph(f"- {bullet}")


def _keyword_score(cv_text: str, required_lines: list[str]) -> int:
    if not required_lines:
        return 100
    hits = sum(1 for line in required_lines if any(tok in cv_text.lower() for tok in line.lower().split()))
    return int((hits / len(required_lines)) * 100)


class CVTailor:
    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def tailor(
        self,
        company: str,
        jd: JDExtractionResult,
        job_id: int | None = None,
    ) -> CVTailorResult:
        if not BASE_CV_PATH.exists():
            raise FileNotFoundError(f"Base CV not found at {BASE_CV_PATH}")

        doc = Document(BASE_CV_PATH)
        base_json = _doc_to_json(doc)

        diff = await self.claude.tailor_cv_gap(base_json, jd.compressed.model_dump(), job_id=job_id)
        _apply_diff(doc, diff)

        final_text = "\n".join(p.text for p in doc.paragraphs)
        score = _keyword_score(final_text, jd.compressed.required_skills)
        match_score = int(max(score, diff.get("match_score", 0)))

        date_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        company_slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in company)[:50].strip("_")
        cv_path = CV_OUTPUT_DIR / f"{company_slug}_{date_str}.docx"
        doc.save(cv_path)

        pdf_path = await self._convert_pdf(cv_path)
        return CVTailorResult(
            cv_path=str(cv_path),
            pdf_path=str(pdf_path) if pdf_path else None,
            match_score=match_score,
            diff=diff,
        )

    async def _convert_pdf(self, docx_path: Path) -> Path | None:
        command = [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            str(docx_path),
            "--outdir",
            str(docx_path.parent),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        pdf_path = docx_path.with_suffix(".pdf")
        return pdf_path if pdf_path.exists() else None


def diff_preview(diff: dict[str, Any]) -> str:
    return json.dumps(diff, indent=2)
