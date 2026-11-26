#!/usr/bin/env python3
"""Add iOS/iPadOS home-screen metadata to the single-file QBank page.

Safari on iPad ignores the W3C web-app manifest; it reads Apple's own meta tags.
With these, "Add to Home Screen" launches the QBank full-screen with no Safari
chrome and its own icon slot, instead of as a plain bookmark.

Idempotent: re-running on an already-tagged page changes nothing.

Usage
    python3 export/add_ios_meta.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "index.html"

MARKER = 'name="apple-mobile-web-app-capable"'

TAGS = """
    <!-- iPad / iPhone: run full-screen when added to the Home Screen.
         Safari ignores the W3C manifest and reads these instead. -->
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="CoreBTR QBank" />
    <meta name="theme-color" content="#0f172a" />
"""

ANCHOR = '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'


def main() -> int:
    if not SOURCE.exists():
        sys.exit(f"{SOURCE} not found")

    html = SOURCE.read_text(encoding="utf-8")
    if MARKER in html:
        print(f"{SOURCE.relative_to(ROOT)} already has the iOS home-screen tags")
        return 0
    if html.count(ANCHOR) != 1:
        sys.exit(f"expected exactly 1 viewport meta tag, found {html.count(ANCHOR)}")

    before = html.count('"correct_answer"')
    html = html.replace(ANCHOR, ANCHOR + TAGS, 1)
    after = html.count('"correct_answer"')

    if after != before:
        sys.exit(f"question count changed {before} -> {after}; aborting")
    if not html.rstrip().endswith("</html>"):
        sys.exit("page no longer ends with </html>; aborting")

    SOURCE.write_text(html, encoding="utf-8")
    print(f"updated {SOURCE.relative_to(ROOT)}  {SOURCE.stat().st_size:,} bytes")
    print(f"  tags added : 5")
    print(f"  questions  : {after:,} (unchanged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
