from __future__ import annotations

import re

import tiktoken
from bs4 import BeautifulSoup


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_form_fields(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    for noisy in soup(["script", "style", "noscript", "svg", "img", "footer", "header", "nav"]):
        noisy.decompose()

    fields = []
    for idx, node in enumerate(soup.select("input, textarea, select, button"), start=1):
        field_type = (node.get("type") or node.name or "text").lower()
        if field_type in {"hidden", "submit", "reset"}:
            continue

        label = node.get("aria-label") or node.get("placeholder") or node.get("name") or node.get("id")
        if not label and node.name == "button":
            label = node.get_text(strip=True)

        fields.append(
            {
                "i": idx,
                "t": field_type,
                "n": _clean(label or f"field_{idx}"),
                "r": bool(node.get("required")),
                "o": [opt.get_text(strip=True) for opt in node.find_all("option")][:20],
            }
        )

    if len(fields) < 2:
        return None

    payload = {"f": fields}
    encoder = tiktoken.get_encoding("cl100k_base")
    text = str(payload)
    token_count = len(encoder.encode(text))

    if token_count > 800:
        # compact to minimal info under budget
        payload["f"] = [{"i": f["i"], "t": f["t"], "n": f["n"]} for f in fields[:40]]
        token_count = len(encoder.encode(str(payload)))

    payload["tc"] = token_count
    return payload
