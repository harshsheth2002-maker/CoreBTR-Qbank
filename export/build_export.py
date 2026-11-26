#!/usr/bin/env python3
"""Derive structured exports from the QBank page.

The QBank lives in this repository as a single self-contained file, `index.html`
(about 50 MB: the app shell plus a `const TESTS_LIST = [...]` payload holding
every test and question).  Earlier revisions split that file into ten 5 MB
chunks to work around GitHub's web-uploader limit; those chunks were replaced by
the single file and remain available in git history at commit 2a844a8.

Usage
    python3 export/build_export.py               # catalog.json, qbank.jsonl, stats.json
    python3 export/build_export.py --full-json   # also tests_list.json (raw array, ~50 MB)

Outputs (written next to this script)
    catalog.json    one row per test (id, title, question count, marks, duration)
    qbank.jsonl     one question per line
    stats.json      totals used in the README
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent
ROOT = EXPORT_DIR.parent
SOURCE = ROOT / "index.html"


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_tests_list(html_path: Path) -> list:
    """Pull the `const TESTS_LIST = [...]` payload out of the page.

    The declaration also appears inside a JS comment, so take the last one and
    bracket-match from there (the payload is JSON, but a naive regex is not safe
    with the escaped strings inside)."""
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    anchor = raw.rindex("const TESTS_LIST =")
    start = raw.index('[{"id"', anchor)

    i, depth, in_string, escaped = start, 0, False, False
    while i < len(raw):
        ch = raw[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return json.loads(raw[start : i + 1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-json", action="store_true",
                        help="also write tests_list.json (the raw TESTS_LIST array)")
    args = parser.parse_args()

    if not SOURCE.exists():
        sys.exit(f"{SOURCE} not found")
    print(f"{SOURCE.name}: {SOURCE.stat().st_size:,} bytes  md5={md5(SOURCE)}")

    tests = extract_tests_list(SOURCE)

    # ---- catalog.json -------------------------------------------------
    catalog = [
        {
            "test_id": t["id"],
            "title": t["title"],
            "num_questions": len(t["questions"]),
            "total_marks": t.get("total_marks"),
            "duration": t.get("duration"),
        }
        for t in tests
    ]
    (EXPORT_DIR / "catalog.json").write_text(
        json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    # ---- qbank.jsonl --------------------------------------------------
    jsonl_path = EXPORT_DIR / "qbank.jsonl"
    n_questions = n_video = n_images = 0
    per_subject: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for test in tests:
            subject = test["id"].split("_")[0]
            per_subject[subject][0] += 1
            for q in test["questions"]:
                per_subject[subject][1] += 1
                n_questions += 1
                if q.get("video"):
                    n_video += 1
                if q.get("question_images"):
                    n_images += 1
                fh.write(
                    json.dumps(
                        {
                            "test_id": test["id"],
                            "test": test["title"],
                            "qid": q["id"],
                            "question": q.get("raw_text") or q.get("text"),
                            "options": {o["label"]: o["text"] for o in q["options"]},
                            "answer": q["correct_answer"],
                            "images": q.get("question_images", []),
                            "video": bool(q.get("video")),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    if args.full_json:
        (EXPORT_DIR / "tests_list.json").write_text(
            json.dumps(tests, ensure_ascii=False), encoding="utf-8"
        )

    # ---- stats.json ---------------------------------------------------
    stats = {
        "tests": len(tests),
        "questions": n_questions,
        "declared_num_questions_sum": sum(t.get("num_questions", 0) for t in tests),
        "questions_with_video_solution": n_video,
        "questions_with_images": n_images,
        "questions_with_explanation": sum(
            1 for t in tests for q in t["questions"] if q.get("explanation")
        ),
        "distinct_image_urls": len({
            u for t in tests for q in t["questions"]
            for u in (q.get("question_images") or []) + (q.get("explanation_images") or [])
        }),
        "subjects": {
            k: {"tests": v[0], "questions": v[1]}
            for k, v in sorted(per_subject.items(), key=lambda kv: -kv[1][1])
        },
        "source_bytes": SOURCE.stat().st_size,
        "source_md5": md5(SOURCE),
        "jsonl_bytes": jsonl_path.stat().st_size,
    }
    (EXPORT_DIR / "stats.json").write_text(
        json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    print(f"tests={stats['tests']} questions={stats['questions']:,} "
          f"declared_sum={stats['declared_num_questions_sum']:,} "
          f"videos={stats['questions_with_video_solution']:,} "
          f"images={stats['questions_with_images']:,} "
          f"distinct_image_urls={stats['distinct_image_urls']:,}")
    if stats["questions"] != stats["declared_num_questions_sum"]:
        print("WARNING: parsed question count != sum of num_questions", file=sys.stderr)
        return 1
    print(f"catalog.json  {os.path.getsize(EXPORT_DIR / 'catalog.json'):,} bytes")
    print(f"qbank.jsonl   {stats['jsonl_bytes']:,} bytes")
    print(f"stats.json    {os.path.getsize(EXPORT_DIR / 'stats.json'):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
