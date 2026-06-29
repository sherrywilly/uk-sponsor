from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None


def extract_form_fields(html: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "svg", "footer", "header", "nav"]):
        tag.decompose()

    fields: list[dict[str, Any]] = []

    for inp in soup.select("input, textarea, select, button"):
        input_type = inp.get("type", inp.name)
        if input_type in {"hidden", "submit"}:
            continue
        label = (
            inp.get("aria-label")
            or inp.get("placeholder")
            or inp.get("name")
            or inp.get("id")
            or inp.get_text(" ", strip=True)
            or ""
        )
        selector = _build_selector(inp)
        if not label and not selector:
            continue
        fields.append(
            {
                "k": label[:80],
                "t": input_type[:30],
                "r": inp.has_attr("required"),
                "s": selector[:120],
                "o": [o.get_text(" ", strip=True)[:50] for o in inp.select("option")[:8]],
            }
        )

    if len(fields) < 2:
        return None

    compact = {"f": fields[:120]}
    compact = _reduce_until_token_target(compact, 800)
    return compact


def serialized_token_count(payload: dict[str, Any]) -> int:
    raw = json.dumps(payload, separators=(",", ":"))
    if tiktoken is None:
        return max(1, len(raw) // 4)
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(raw))


def _build_selector(inp: Any) -> str:
    if inp.get("id"):
        return f"#{inp['id']}"
    if inp.get("name"):
        return f"[name='{inp['name']}']"
    classes = " ".join(inp.get("class", [])[:3]).strip()
    if classes:
        return f"{inp.name}.{'.'.join(classes.split())}"
    return inp.name


def _reduce_until_token_target(payload: dict[str, Any], target: int) -> dict[str, Any]:
    if serialized_token_count(payload) <= target:
        return payload
    fields = payload.get("f", [])
    for f in fields:
        f.pop("o", None)
    if serialized_token_count(payload) <= target:
        return payload
    payload["f"] = fields[: max(2, len(fields) // 2)]
    if serialized_token_count(payload) <= target:
        return payload
    for f in payload["f"]:
        f["k"] = re.sub(r"\s+", " ", f.get("k", ""))[:24]
        f["s"] = f.get("s", "")[:32]
    return payload
