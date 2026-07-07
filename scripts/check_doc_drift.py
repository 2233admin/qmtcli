"""Detect drift between the official xtdata/xttrader doc pages and this repo's alignment matrices.

Stdlib only (urllib.request + re + html), no third-party dependencies, meant to run in CI
(.github/workflows/doc-drift.yml) as well as locally.

For each doc page, this extracts every function name from the first line of each H4 section's first
``language-python`` code block (its usage signature, e.g. ``get_market_data_ex(field_list=[], ...)``
-> ``get_market_data_ex``). It then checks that every extracted name appears, backticked, somewhere
in the first column of a markdown table row in docs/xtdata-alignment.md or
docs/xttrader-alignment.md (the two matrices are checked as a combined set, since a handful of
xttrader-flavored names like ``subscribe``/``unsubscribe`` are documented as "internal, auto on
connect" rather than pinned to one specific matrix file).

This is a one-directional check: doc -> matrix. Matrix rows that reference functions/methods not on
the doc page at all (for example ``get_market_data_ex``, ``download_history_data2``,
``get_l2_quote``, which are real xtquant functions but are not documented as their own H4 section on
the public doc page) are expected and must NOT fail the check.

A network fetch failure exits 0 with a warning printed to stderr, since a flaky network must not
false-alarm a CI schedule; only an actual detected gap between a successfully fetched doc page and
the matrices exits 1.

Run with: ``python scripts/check_doc_drift.py``
"""

from __future__ import annotations

import html
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

XTDATA_DOC_URL = "https://dict.thinktrader.net/nativeApi/xtdata.html"
XTTRADER_DOC_URL = "https://dict.thinktrader.net/nativeApi/xttrader.html"

REPO_ROOT = Path(__file__).resolve().parent.parent
XTDATA_MATRIX_PATH = REPO_ROOT / "docs" / "xtdata-alignment.md"
XTTRADER_MATRIX_PATH = REPO_ROOT / "docs" / "xttrader-alignment.md"

H4_SECTION_RE = re.compile(r'<h4[^>]*id="[^"]*"[^>]*>[\s\S]*?</h4>([\s\S]*?)(?=<h[234]|$)')
CODE_BLOCK_RE = re.compile(r'<div class="language-python[^"]*"[\s\S]*?<code>([\s\S]*?)</code>')
FIRST_LINE_RE = re.compile(r'<span class="line">([\s\S]*?)</span>\n')
SIGNATURE_RE = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*\(")
BACKTICKED_NAME_RE = re.compile(r"`([a-z_][a-z0-9_]*)`")


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "qmtcli-doc-drift-check"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_doc_function_names(doc_html: str) -> set[str]:
    names: set[str] = set()
    for section_match in H4_SECTION_RE.finditer(doc_html):
        tail = section_match.group(1)
        code_match = CODE_BLOCK_RE.search(tail)
        if not code_match:
            continue
        code_html = code_match.group(1)
        line_match = FIRST_LINE_RE.search(code_html)
        raw_line = line_match.group(1) if line_match else code_html.split("\n", 1)[0]
        text = html.unescape(re.sub(r"<[^>]+>", "", raw_line)).strip()
        sig_match = SIGNATURE_RE.match(text)
        if sig_match:
            names.add(sig_match.group(1))
    return names


def extract_matrix_function_names(markdown_text: str) -> set[str]:
    """Backticked names in the first column of every markdown table row.

    Header/separator rows (``| xtdata function | ... |``, ``| --- | ... |``) contribute nothing
    since they contain no backticks, so no special-casing is needed for them.
    """
    names: set[str] = set()
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = stripped.strip("|").split("|")
        if not cells:
            continue
        names.update(BACKTICKED_NAME_RE.findall(cells[0]))
    return names


def main() -> int:
    try:
        xtdata_html = fetch(XTDATA_DOC_URL)
        xttrader_html = fetch(XTTRADER_DOC_URL)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"WARNING: could not fetch doc pages ({exc}); skipping drift check.", file=sys.stderr)
        return 0

    matrix_names: set[str] = set()
    matrix_names |= extract_matrix_function_names(XTDATA_MATRIX_PATH.read_text(encoding="utf-8"))
    matrix_names |= extract_matrix_function_names(XTTRADER_MATRIX_PATH.read_text(encoding="utf-8"))

    drift_found = False
    for label, doc_html in (("xtdata.html", xtdata_html), ("xttrader.html", xttrader_html)):
        doc_names = extract_doc_function_names(doc_html)
        missing = sorted(doc_names - matrix_names)
        print(f"{label}: {len(doc_names)} functions extracted, {len(missing)} missing from matrix")
        if missing:
            drift_found = True
            print(f"  MISSING (added on the doc page, absent from the alignment matrices): {missing}")

    if drift_found:
        print(
            "\nDrift detected: add the missing function name(s) above to "
            "docs/xtdata-alignment.md or docs/xttrader-alignment.md.",
            file=sys.stderr,
        )
        return 1

    print("\nNo drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
