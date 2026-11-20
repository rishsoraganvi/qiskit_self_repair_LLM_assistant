"""Pull Python code out of a model response (rules in docs/PROMPTS.md)."""
from __future__ import annotations

import re

_PY_BLOCK = re.compile(r"```[ \t]*(?:python|py|python3)[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_BLOCK = re.compile(r"```[^\n`]*\r?\n(.*?)```", re.DOTALL)

NO_FUNCTION_FOUND = "no_function_found"


def extract_code(text: str | None) -> str:
    """Last ```python block, else last fenced block of any kind, else the raw text; stripped."""
    text = text or ""
    for pattern in (_PY_BLOCK, _ANY_BLOCK):
        blocks = pattern.findall(text)
        if blocks:
            return blocks[-1].strip()
    return text.strip()


def has_function(code: str, entry_point: str) -> bool:
    return re.search(rf"^\s*(?:async\s+)?def\s+{re.escape(entry_point)}\s*\(", code, re.MULTILINE) is not None


def extraction_note(code: str, entry_point: str) -> str:
    return "" if has_function(code, entry_point) else NO_FUNCTION_FOUND
