#!/usr/bin/env python3
"""Prince Edward Island provincial statute lookup (verbatim) from the official
Legislative Counsel Office consolidation PDFs on princeedwardisland.ca.

Usage:
    pe_law.py H-5 1         # Highway Traffic Act, s. 1 (Definitions)
    pe_law.py H-5 2         # s. 2 (Administration)
    pe_law.py H-5 --toc     # list section headings

Input: statute id (chapter, e.g. H-5) + a section number. The script downloads
the official LCO office-consolidation PDF from www.princeedwardisland.ca,
converts it with pdftotext -layout, locates the numbered section in the body
(ignoring the table of contents and all page furniture), and returns the text
verbatim with heading, citation, source URL and retrieval date.

Anti-fabrication: never paraphrases and never fabricates. It only prints text
that actually appears in the official PDF. If the section isn't found, or the
PDF can't be fetched, it exits non-zero with a clear error.

Exit codes: 0 found; 1 not found / usage; 2 network / conversion error.
"""
from __future__ import annotations

import argparse, hashlib, os, re, shutil, subprocess, sys, tempfile, urllib.request
from datetime import date
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) ca-law-skill/1.0"
TIMEOUT = 90

# Registry of PEI statutes: id -> (title, consolidated citation, PDF URL).
# The current-to date lives inside each PDF's PLEASE NOTE block / page footers.
STATUTES = {
    "H-5": (
        "Highway Traffic Act",
        "R.S.P.E.I. 1988, Cap. H-5",
        "https://www.princeedwardisland.ca/sites/default/files/legislation/h-05-highway_traffic_act.pdf",
    ),
}


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def st_cache() -> Path:
    d = hermes_home() / "plugin-data" / "ca-law" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_pdf(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def pdf_to_text(data: bytes) -> str:
    """Run pdftotext -layout on the PDF bytes and return the plain text."""
    if not shutil.which("pdftotext"):
        sys.exit("pe-law: pdftotext not found on PATH (expected at /usr/sbin/pdftotext)")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        pdf = f.name
    txt = pdf + ".txt"
    try:
        r = subprocess.run(["pdftotext", "-layout", pdf, txt],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("pe-law: pdftotext failed: " + r.stderr)
        with open(txt, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    finally:
        for p in (pdf, txt):
            try:
                os.unlink(p)
            except OSError:
                pass


# A section header: optional indent, number ("1", "1.1", "3"), a dot, two+
# spaces, then an uppercase-initial heading with NO periods (so it can't match
# dotted TOC leader lines or historical citations). Heading chars deliberately
# exclude '.' to reject table-of-contents rows like "1.  Definitions...... 13".
HEADER_RE = re.compile(
    r"^[ \t]*(\d+(?:\.\d+)*)\.\s{2,}"
    r"([A-Z][A-Za-z0-9 ,&'()/\-]{1,})$"
)

# Page furniture to strip from the body region (running page headers/footers).
FURNITURE_RE = re.compile(
    r"^\s*(?:"
    r"Page\s+\d+|"
    r"Current to:.*|"
    r"c\s*t\s*Current to:.*|"          # page footer "c t   Current to: <date>"
    r"c\s*t\s*$|"                      # bare footer marker
    r"PART\s+[IVXLC]+(?:\s+-\s+[A-Z '-]+)?|"
    r"Section\s+\d+.*Highway Traffic Act|"
    r"Highway Traffic Act\s+Section\s+\d+.*|"   # running footer, reversed
    r"Highway Traffic Act\s*$"
    r")"
)


def parse_headers(text: str) -> list[tuple[int, str, str]]:
    """Return genuine body section headers as [(line_index, number, heading)].

    Every line is tested against HEADER_RE. TOC rows never match because their
    headings are followed by dotted leaders to the page number ('.' is excluded
    from the heading character class), so matches are the real body headers.
    """
    out: list[tuple[int, str, str]] = []
    for i, raw in enumerate(text.splitlines()):
        m = HEADER_RE.match(raw)
        if m:
            out.append((i, m.group(1), m.group(2).strip()))
    return out


def extract_section(text: str, headers: list[tuple[int, str, str]],
                    target: str) -> str | None:
    """Return the clean verbatim body for the section whose number == target.

    Body = lines strictly between the target header line and the next detected
    header line, with page furniture (running headers/footers, form feeds,
    "Page N", "Current to:...", "PART ..." banners) stripped.
    """
    idxs = [j for j, (_, num, _h) in enumerate(headers) if num == target]
    if not idxs:
        return None
    j = idxs[0]
    start_li = headers[j][0]
    end_li = headers[j + 1][0] if j + 1 < len(headers) else len(text.splitlines())
    body_lines = []
    for raw in text.splitlines()[start_li + 1: end_li]:
        if FURNITURE_RE.match(raw):
            continue
        s = raw.replace("\f", "").strip()
        if s:
            body_lines.append(raw.rstrip())
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    return "\n".join(body_lines).strip()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prince Edward Island statute lookup (LCO consolidation PDFs)")
    ap.add_argument("statute", help="statute id / chapter, e.g. H-5")
    ap.add_argument("args", nargs="*", help="section number, or --toc")
    ap.add_argument("--toc", action="store_true",
                    help="list all numbered section headings and exit")
    a = ap.parse_args()

    sid = a.statute.upper()
    if sid not in STATUTES:
        print("pe-law: unknown statute '%s'. Registered: %s"
              % (a.statute, ", ".join(sorted(STATUTES))), file=sys.stderr)
        return 1
    title, citation, url = STATUTES[sid]

    cp = st_cache() / ("pe-raw-" + re.sub(r"[^A-Za-z0-9._-]", "_", sid) + ".pdf")
    if cp.exists():
        data = cp.read_bytes()
        source = url + " [cached]"
    else:
        try:
            data = download_pdf(url)
        except Exception as e:
            print(f"pe-law: network error fetching {url}: {e}", file=sys.stderr)
            return 2
        source = url
        cp.write_bytes(data)

    text = pdf_to_text(data)
    headers = parse_headers(text)
    if not headers:
        print("pe-law: could not parse any section headers from the PDF.", file=sys.stderr)
        return 2

    args_l = [x.lower() for x in a.args]
    if a.toc or "--toc" in args_l or "toc" in args_l:
        for li, num, hd in headers:
            print(f"{num:<8} {hd}")
        print(f"\n-- {len(headers)} numbered sections in {title} ({citation})")
        return 0

    num_arg = " ".join(a.args).strip()
    m = re.match(r"^(?:s\.?\s*|section\s*)?(\d+(?:\.\d+)*)", num_arg, re.I)
    target = m.group(1) if m else num_arg
    body = extract_section(text, headers, target)
    if body is None:
        got = sorted({n for _, n, _h in headers})
        print(f"pe-law: {title} ({citation}) has no numbered section '{target}'.", file=sys.stderr)
        print(f"Sample sections: {', '.join(got[:40])}. Use --toc.", file=sys.stderr)
        return 1

    heading = next((h for _, n, h in headers if n == target), "")
    print(f"{target} — {heading}")
    print("=" * 70)
    print(body)
    print("=" * 70)
    print(f"{title} — {citation}")
    print(f"Source: {source}")
    print(f"Retrieved: {date.today().isoformat()} (mode: PDF via pdftotext -layout)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
