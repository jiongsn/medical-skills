#!/usr/bin/env python3
"""Validate medical-guideline-parser-v2 markdown output.

This is a lightweight deterministic QA pass. It cannot judge medical correctness;
it catches common process failures: shortcut placeholders, missing required
sections, and missing coverage ledger.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FORBIDDEN_PATTERNS = [
    (re.compile(r"节选"), "Found '节选' placeholder"),
    (re.compile(r"representative sample", re.I), "Found 'representative sample' placeholder"),
    (re.compile(r"core fields?\s*\(excerpt\)", re.I), "Found 'core fields (excerpt)' placeholder"),
    (re.compile(r"详见参考"), "Found '详见参考' placeholder"),
    (re.compile(r"see\s+(v1|reference)", re.I), "Found 'see v1/reference' placeholder"),
    (re.compile(r"\.\.\.|……"), "Found ellipsis placeholder"),
    (re.compile(r"\betc\.", re.I), "Found 'etc.' placeholder"),
]

REQUIRED_SECTION_PATTERNS = [
    (re.compile(r"(Logic Tree|Clinical Logic|诊疗逻辑|逻辑树)", re.I), "logic tree / clinical logic section"),
    (re.compile(r"(Entity Inventory|实体清单|实体列表)", re.I), "entity inventory section"),
    (re.compile(r"(Coverage Ledger|章节覆盖|覆盖表)", re.I), "coverage ledger section"),
]

ENTITY_TABLE_HINT = re.compile(r"\|\s*(Entity|实体)\s*\|\s*(Type|类型)\s*\|", re.I)
COVERAGE_TABLE_HINT = re.compile(r"\|\s*(Guideline section|指南章节|章节)\s*\|.*\|\s*(Entity count|实体数|实体数量)\s*\|", re.I)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate medical-guideline-parser-v2 markdown output")
    parser.add_argument("markdown", type=Path, help="Path to the parser output markdown file")
    args = parser.parse_args()

    if not args.markdown.exists():
        print(f"ERROR: file not found: {args.markdown}", file=sys.stderr)
        return 2

    text = args.markdown.read_text(encoding="utf-8", errors="replace")
    failures: list[str] = []
    warnings: list[str] = []

    for pattern, message in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            failures.append(message)

    for pattern, label in REQUIRED_SECTION_PATTERNS:
        if not pattern.search(text):
            failures.append(f"Missing required {label}")

    if not ENTITY_TABLE_HINT.search(text):
        failures.append("Missing entity inventory table header")

    if not COVERAGE_TABLE_HINT.search(text):
        failures.append("Missing coverage ledger table header with entity count")

    # Suspicious but not always fatal: a coverage ledger row with zero entities and no explicit gap reason.
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0] in {"guideline section", "指南章节", "章节", "---"}:
            continue
        if any(c == "0" for c in cells[1:4]) and not any(
            token in line.lower() for token in ["not_present", "not applicable", "not_applicable", "unresolved", "gap", "不适用", "未提及", "缺口"]
        ):
            warnings.append(f"Line {line_no}: zero entity/logical coverage without explicit gap reason")

    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
    else:
        print("PASS")

    if warnings:
        print("WARNINGS")
        for item in warnings:
            print(f"- {item}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
