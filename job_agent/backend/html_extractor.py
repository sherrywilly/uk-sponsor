from __future__ import annotations

import json
from typing import Any

import tiktoken
from bs4 import BeautifulSoup


def _token_count(payload: dict[str, Any]) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(json.dumps(payload, ensure_ascii=False)))


def extract_form_fields(html: str, token_limit: int = 800) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "lxml")

    fields = []
    for element in soup.select("input, textarea, select, button"):
        field_type = element.get("type") or element.name
        if field_type in {"hidden", "submit", "button"} and element.name == "input":
            continue
        name = element.get("name") or element.get("id") or ""
        label = element.get("aria-label") or element.get("placeholder") or name
        if not label:
            continue
        fields.append(
            {
                "n": name,
                "l": label,
                "t": field_type,
                "r": element.has_attr("required"),
                "o": [o.get_text(strip=True) for o in element.find_all("option")][:20] if element.name == "select" else [],
            }
        )

    if len(fields) < 2:
        return None

    payload = {"f": fields[:80]}
    while _token_count(payload) > token_limit and len(payload["f"]) > 2:
        payload["f"] = payload["f"][:-2]

    return payload
