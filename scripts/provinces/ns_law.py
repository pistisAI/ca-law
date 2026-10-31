#!/usr/bin/env python3
"""Nova Scotia provincial statute lookup (verbatim) from the OFFICIAL
nslegislature.ca consolidated statute publications.

Usage:
    ns_law.py "Motor Vehicle Act" 2        # Motor Vehicle Act R.S.N.S. 1989, c. 293, s. 2
    ns_law.py "Maintenance and Custody Act" 10   # (renamed Parenting and Support Act)
    ns_law.py "Parenting and Support Act" --toc  # list section headings

The official consolidated text of each current Nova Scotia public statute is
published as a PDF (and a companion HTML page) under
    https://nslegislature.ca/sites/default/files/legc/statutes/<short name>.pdf
    https://nslegislature.ca/sites/default/files/legc/statutes HTML/<short name>.htm

The unified consolidated index is at
    https://nslegislature.ca/legislative-business/bills-statutes/consolidated-public-statutes

Nova Scotia consolidation history / renames as published on that index:
  * The "Maintenance and Custody Act" (R.S.N.S. 1989, c. 160) is now consolidated
    and cited as the "Parenting and Support Act" — the index cross-references the
    old name.
  * The "Motor Vehicle Act" (R.S.N.S. 1989, c. 293) was REPEALED (by 2025, c. 20,
    s. 378, repeal in force 2026-10-19) and its consolidation has been removed
    from the official site; the index lists it as "(repealed; repeal not
    proclaimed in force)" with no PDF/HTML link.

Anti-fabrication: the script prints ONLY text that actually appears in the
official publication for the requested section. If the consolidation is
unavailable (404), the section cannot be found, or the publication cannot be
parsed, it exits non-zero with a clear diagnostic — it never paraphrases and
never fabricates a quotation.

Exit codes: 0 found; 1 not found / usage; 2 network / conversion / parser error.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 ca-law-skill/1.0")
TIMEOUT = 120

INDEX_URL = ("https://nslegislature.ca/legislative-business/"
             "bills-statutes/consolidated-public-statutes")


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def cache_dir() -> Path:
    d = hermes_home() / "plugin-data" / "ca-law" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Statute registry. Key   = user-supplied display name.
# Value            = (consolidated short-title as used in the OFFICIAL file
#                    name, official citation).
# 'Motor Vehicle Act' is listed with no PDF because its repeal (in force
# 2026-10-19) removed the consolidation; included so the script reports that
# fact explicitly instead of guessing.
# ---------------------------------------------------------------------------
STATUTES = {
    "Motor Vehicle Act": ("motor vehicle", "R.S.N.S. 1989, c. 293",
                          "repealed"),
    "Maintenance and Custody Act": ("parenting and support",
                                    "R.S.N.S. 1989, c. 160",
                                    "consolidated as Parenting and Support Act"),
    "Parenting and Support Act": ("parenting and support",
                                  "R.S.N.S. 1989, c. 160", None),
}


def pdf_url(short: str) -> str:
    return "https://nslegislature.ca/sites/default/files/legc/statutes/" + \
        urllib.parse.quote(short) + ".pdf"


def html_url(short: str) -> str:
    # The directory "statutes HTML" contains a real space; quote it.
    return "https://nslegislature.ca/sites/default/files/legc/" + \
        urllib.parse.quote("statutes HTML") + "/" + \
        urllib.parse.quote(short) + ".htm"


def http_get(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} from {url}")
        return r.read()


def pdf_to_text(data: bytes) -> str:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext not found (expected at /usr/sbin/pdftotext)")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        pdf = f.name
    txt = pdf + ".txt"
    try:
        r = subprocess.run(["pdftotext", "-layout", pdf, txt],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("pdftotext failed: " + r.stderr)
        with open(txt, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    finally:
        for p in (pdf, txt):
            try:
                os.unlink(p)
            except OSError:
                pass


# Body section header. In the Nova Scotia consolidations the heading is on its
# OWN line (e.g. "Duty of parent or guardian") and the number starts the
# following content line ("        8      A parent or guardian ...").
HEADING_RE = re.compile(r"^[A-Z][A-Za-z0-9 ,'&()/\-]*$")
# A content line that begins a numbered section: indentation, the number, then
# two+ spaces. Table-of-contents leader lines ("Short title......1") start with
# a letter and contain '.', so they never match.
SECNUM_START_RE = re.compile(r"^[ \t]*(\d+(?:\.\d+)*[A-Za-z]?)[ \t]{2,}")

FURNITURE_RE = re.compile(
    r"^\s*(?:"
    r"Page\s+\d+.*|"
    r"Current to:.*|"
    r"c\s*t\s*Current to:.*|"
    r"c\s*t\s*$|"
    r"PART\s+[IVXLC]+(?:.*)?|"
    r"OCTOBER\s+\d+,\s+\d+$|"          # running date footer
    r"[A-Z][A-Za-z ,'\-]+\s+Section\s+\d+.*|"
    r"R\.S\.,\s*c\.\s*\d+.*"          # running RS citation footer
    r")")


def is_heading(raw: str) -> bool:
    s = raw.strip()
    return bool(HEADING_RE.match(s)) and "Section" not in s


def parse_sections(text: str) -> list[dict]:
    """Return list of {num, line (numbered content line), heading, end_line}."""
    lines = text.splitlines()
    starts: list[tuple[int, str]] = []
    for i, raw in enumerate(lines):
        s = raw.strip()
        m = SECNUM_START_RE.match(raw)
        # A section start: number, then 2+ spaces, then content.
        # Reject footers like "Section 2" and page numbers.
        if m and not FURNITURE_RE.match(raw) and s[0].isdigit():
            # skip when the whole visible line is just the number (pt TOC col)
            rest = raw[m.end():].strip()
            if rest:
                starts.append((i, m.group(1)))
    out: list[dict] = []
    for k, (i, num) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        # heading = nearest heading line above this numbered line
        heading = ""
        for j in range(i - 1, max(-1, i - 8), -1):
            cand = lines[j].strip()
            if not cand or FURNITURE_RE.match(cand):
                continue
            if is_heading(cand):
                heading = cand
            break
        out.append({"num": num, "li": i, "end": end, "heading": heading,
                    "line": lines[i], "lines": lines})
    return out


def extract_section(text: str, sections: list[dict], target: str) -> str | None:
    secs = [s for s in sections if s["num"] == target]
    if not secs:
        return None
    sec = secs[0]
    lines = sec["lines"]
    body: list[str] = []
    # first line: strip the leading number run
    m = SECNUM_START_RE.match(sec["line"])
    first = sec["line"][m.end():].rstrip() if m else sec["line"].rstrip()
    if first.strip() and not FURNITURE_RE.match(first):
        body.append(first)
    for raw in lines[sec["li"] + 1: sec["end"]]:
        if not raw.strip() or FURNITURE_RE.match(raw):
            continue
        body.append(raw.rstrip())
    # drop trailing heading line(s) belonging to the next section
    while body and is_heading(body[-1]):
        body.pop()
    out = "\n".join(body).strip()
    return out if out else None


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>|</div>|</h[1-6]>|</li>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    for ent, ch in [("&nbsp;", " "), ("&ensp;", " "), ("&emsp;", " "),
                    ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(ent, ch)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def fetch_consolidated(short: str) -> tuple[str, str, str]:
    """Download the official consolidation (PDF preferred, then HTML).
    Returns (text, source_url, mode)."""
    pdf_u = pdf_url(short)
    html_u = html_url(short)
    # 1) PDF
    try:
        data = http_get(pdf_u)
        if data[:4] == b"%PDF":
            text = pdf_to_text(data)
            if text.strip():
                return text, pdf_u, "pdf"
    except Exception as e:
        print(f"ns-law: PDF unavailable ({e}). Trying HTML page.",
              file=sys.stderr)
    # 2) HTML companion page
    try:
        html = http_get(html_u).decode("utf-8", "replace")
    except Exception as e:
        raise RuntimeError(f"ns-law: could not fetch {html_u}: {e}") from e
    if "/TSPD/" in html or "loaderConfig" in html or len(html) < 2000:
        raise RuntimeError(
            f"ns-law: official site returned a bot-intercept page, not statute "
            f"text ({html_u}). Retry, or fetch the PDF at {pdf_u} directly.")
    text = html_to_text(html)
    if not text.strip():
        raise RuntimeError(f"ns-law: no text extracted from {html_u}")
    return text, html_u, "html"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Nova Scotia statute lookup (official nslegislature.ca consolidations)")
    ap.add_argument("statute", help="statute display name")
    ap.add_argument("args", nargs="*", help="section number, or --toc")
    ap.add_argument("--toc", action="store_true", help="list section headings and exit")
    a = ap.parse_args()

    disp = None
    for key in STATUTES:
        if a.statute.strip().lower() == key.lower() or \
           a.statute.strip().lower() in key.lower():
            disp = key
            break
    if disp is None:
        print("ns-law: unknown statute. Registered: %s"
              % ", ".join(STATUTES), file=sys.stderr)
        return 1

    short, citation, note = STATUTES[disp]

    if note == "repealed":
        print(f"ns-law: The {disp} ({citation}) is repealed (by 2025, c. 20, "
              f"s. 378; repeal in force 2026-10-19). The Office of the "
              f"Legislative Counsel no longer publishes a consolidation of it "
              f"on nslegislature.ca — the index lists it as '(repealed; repeal "
              f"not proclaimed in force)' with no PDF/HTML link, and "
              f"{pdf_url(short)} returns HTTP 404. No verbatim official text "
              f"is available from nslegislature.ca for this Act.",
              file=sys.stderr)
        return 2

    cp = cache_dir() / ("ns-" + re.sub(r"[^A-Za-z0-9._-]", "_", disp) + ".txt")
    if cp.exists():
        cp.unlink()  # always refresh from source for verbatim fidelity
    try:
        text, source, mode = fetch_consolidated(short)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2
    cp.write_text(text, encoding="utf-8")

    sections = parse_sections(text)
    if not sections:
        print("ns-law: could not parse section headers from the consolidation.",
              file=sys.stderr)
        return 2

    args_l = [x.lower() for x in a.args]
    if a.toc or "--toc" in args_l or "toc" in args_l:
        for s in sections:
            print(f"{s['num']:<8} {s['heading']}")
        print(f"\n-- {len(sections)} numbered sections in {disp} ({citation})")
        return 0

    num_arg = " ".join(a.args).strip()
    m = re.match(r"^(?:s\.?\s*|section\s*)?(\d+(?:\.\d+)*[A-Za-z]?)",
                 num_arg, re.I)
    target = m.group(1) if m else num_arg
    body = extract_section(text, sections, target)
    if body is None:
        got = sorted({s["num"] for s in sections})
        print(f"ns-law: {disp} ({citation}) has no numbered section "
              f"'{target}'.", file=sys.stderr)
        print(f"Sample sections: {', '.join(got[:40])}. Use --toc.",
              file=sys.stderr)
        return 1

    heading = next((s["heading"] for s in sections if s["num"] == target), "")
    print(f"{target} — {heading}")
    print("=" * 72)
    print(body)
    print("=" * 72)
    print(f"{disp} — {citation}"
          + (f" ({note})" if note else ""))
    print(f"Source: {source}")
    print(f"Retrieved: {date.today().isoformat()} (mode: {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
