#!/usr/bin/env python3
"""Run the deterministic diagnosis demo on synthetic reviewed grades."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from labtrace.diagnosis import build_class_diagnosis  # noqa: E402


def main() -> None:
    source = ROOT / "data" / "synthetic" / "grade_records.json"
    records = json.loads(source.read_text(encoding="utf-8"))
    diagnosis = build_class_diagnosis(records)
    print(json.dumps(diagnosis, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
