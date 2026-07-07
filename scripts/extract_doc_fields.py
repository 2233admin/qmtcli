"""Generate src/qmtcli/xtdata_fields.json from the official xtdata doc appendix.

Stdlib only (urllib.request + re + json + html), no third-party dependencies, so this can run in
any CI or dev environment without installing the project.

The xtdata doc page (https://dict.thinktrader.net/nativeApi/xtdata.html) is a VuePress site: every
heading gets an anchor id, and each field-dictionary appendix section's first code block lists one
field per line as ``'fieldName'          #中文说明`` (with syntax-highlighting spans around each
token). This script:

1. Fetches the page.
2. For each known appendix section (by heading tag + anchor id), slices the HTML from that heading
   to the next h2/h3/h4 (or end of document).
3. Takes the first ``language-python`` code block in that slice, strips HTML tags, unescapes HTML
   entities, and parses ``'name'  #desc`` lines into ``{"name": ..., "desc": ...}``.
4. Writes the combined catalog as JSON to src/qmtcli/xtdata_fields.json.

Run with: ``python scripts/extract_doc_fields.py``
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

DOC_URL = "https://dict.thinktrader.net/nativeApi/xtdata.html"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "src" / "qmtcli" / "xtdata_fields.json"

# (kind, heading tag, heading anchor id) for every field-dictionary appendix section on the doc
# page. Anchor ids are copied verbatim from the rendered HTML (VuePress slugifies Chinese/mixed
# titles into these exact strings, including the leading "_" for the id that would otherwise start
# with a digit).
KIND_SECTIONS: list[tuple[str, str, str]] = [
    ("tick", "h4", "tick-分笔数据"),
    ("kline", "h4", "_1m-5m-1d-k线数据"),
    ("divid", "h4", "除权数据"),
    ("l2quote", "h4", "l2quote-level2实时行情快照"),
    ("l2order", "h4", "l2order-level2逐笔委托"),
    ("l2transaction", "h4", "l2transaction-level2逐笔成交"),
    ("l2quoteaux", "h4", "l2quoteaux-level2实时行情补充-总买总卖"),
    ("l2orderqueue", "h4", "l2orderqueue-level2委买委卖一档委托队列"),
    ("balance", "h4", "balance-资产负债表"),
    ("income", "h4", "income-利润表"),
    ("cashflow", "h4", "cashflow-现金流量表"),
    ("pershareindex", "h4", "pershareindex-主要指标"),
    ("capital", "h4", "capital-股本表"),
    ("top10holder", "h4", "top10holder-top10flowholder-十大股东-十大流通股东"),
    ("holdernum", "h4", "holdernum-股东数"),
    ("instrument", "h3", "合约信息字段列表"),
]

FIELD_LINE_RE = re.compile(r"'([A-Za-z_][A-Za-z0-9_]*)'\s*,?\s*#\s*(.*)")


def fetch_doc_html(url: str = DOC_URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "qmtcli-doc-extractor"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _section_slice(doc_html: str, tag: str, anchor_id: str) -> tuple[str, str]:
    """Return (title_text, tail_html) for the heading with the given tag/anchor id.

    ``tail_html`` runs from just after the heading's closing tag up to (but not including) the next
    h2/h3/h4 heading, or the end of the document.
    """
    pattern = re.compile(
        r'<' + tag + r'[^>]*id="' + re.escape(anchor_id) + r'"[^>]*>([\s\S]*?)</' + tag + r'>([\s\S]*?)(?=<h[234]|$)'
    )
    match = pattern.search(doc_html)
    if not match:
        raise ValueError(f"heading not found: <{tag} id={anchor_id!r}>")
    title_text = html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
    # The VuePress anchor link's visible text is a literal "#" placed right before the heading
    # text; tag-stripping leaves it behind (e.g. "# tick - 分笔数据"), so drop it.
    title_text = re.sub(r"^#\s*", "", title_text)
    return title_text, match.group(2)


def _first_code_block_text(tail_html: str) -> str:
    """Return the plain-text contents of the first ``language-python`` code block in ``tail_html``."""
    match = re.search(r'<div class="language-python[^"]*"[\s\S]*?<code>([\s\S]*?)</code>', tail_html)
    if not match:
        raise ValueError("no language-python code block found in section")
    stripped = re.sub(r"<[^>]+>", "", match.group(1))
    return html.unescape(stripped)


def _parse_fields(code_text: str) -> list[dict[str, str]]:
    fields = []
    for line in code_text.splitlines():
        match = FIELD_LINE_RE.match(line.strip())
        if match:
            fields.append({"name": match.group(1), "desc": match.group(2).strip()})
    return fields


def build_catalog(doc_html: str) -> dict[str, Any]:
    catalog: dict[str, Any] = {}
    errors: list[str] = []
    for kind, tag, anchor_id in KIND_SECTIONS:
        try:
            title, tail_html = _section_slice(doc_html, tag, anchor_id)
            code_text = _first_code_block_text(tail_html)
            fields = _parse_fields(code_text)
        except ValueError as exc:
            errors.append(f"{kind} ({anchor_id}): {exc}")
            continue
        if not fields:
            errors.append(f"{kind} ({anchor_id}): parsed zero fields, regex likely needs adjusting")
            continue
        catalog[kind] = {"title": title, "source_section": anchor_id, "fields": fields}

    if errors:
        raise RuntimeError("field extraction produced empty/broken kinds:\n" + "\n".join(errors))
    return catalog


def main() -> int:
    doc_html = fetch_doc_html()
    catalog = build_catalog(doc_html)

    print(f"Extracted {len(catalog)} field kinds from {DOC_URL}:")
    for kind, entry in catalog.items():
        print(f"  {kind:<15} {len(entry['fields']):>3} fields  ({entry['title']})")

    OUTPUT_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
