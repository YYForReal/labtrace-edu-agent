"""Small privacy helpers for public demo and evaluation assets."""

from __future__ import annotations

import re
from typing import Iterable


_PATTERNS = {
    "email": re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    "phone_cn": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "national_id_cn": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
}


def find_sensitive_data(text: str) -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for kind, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(
                {
                    "kind": kind,
                    "start": match.start(),
                    "end": match.end(),
                    "masked": f"<{kind}>",
                }
            )
    return sorted(findings, key=lambda item: int(item["start"]))


def pseudonymize(
    text: str,
    *,
    student_name: str | None = None,
    student_id: str | None = None,
    extra_terms: Iterable[str] = (),
) -> str:
    result = text
    replacements = [
        (student_name, "<student_name>"),
        (student_id, "<student_id>"),
        *((term, "<redacted>") for term in extra_terms),
    ]
    for raw, replacement in replacements:
        if raw:
            result = result.replace(raw, replacement)
    for kind, pattern in _PATTERNS.items():
        result = pattern.sub(f"<{kind}>", result)
    return result
