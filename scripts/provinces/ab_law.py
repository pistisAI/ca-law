#!/usr/bin/env python3
"""Alberta statute section lookup from the official Alberta King's Printer.

The official consolidated text of Alberta's Revised Statutes of Alberta 2000
acts is served as PDF by the King's Printer at kings-printer.alberta.ca
(the old www.qp.alberta.ca redirects there). Each RSA chapter is a single PDF:

    https://kings-printer.alberta.ca/documents/Acts/{CODE}.pdf

where CODE is the chapter letters plus the zero-padded chapter number,
e.g. Traffic Safety Act, RSA 2000 c T-6  ->  T06  ->  T06.pdf.

We download the PDF, extract layout text with pdftotext, locate the requested
section by its number, and return its VERBATIM body text (running headers,
page numbers and history footers stripped) plus the citation, source URL and
retrieval date. Never paraphrases a statute.

Usage:
    ab_law.py T-6 1          # Traffic Safety Act, s.1 (Definitions)
    ab_law.py T-6 1.1        # s.1.1
    ab_law.py T-6 --search  registrar

Exit codes: 0 found; 1 not found/usage; 2 network/source error.

pid is a chapter id like "T-6". Run from anywhere.
"""
from __future__ import annotations

import argparse, os, re, subprocess, sys, urllib.request, shutil
from datetime import date
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) ca-law-skill/ab/1.0"
TIMEOUT = 90
BASE = "https://kings-printer.alberta.ca/documents/Acts"


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def chapter_to_code(pid: str) -> str:
    """'T-6' -> 'T06'.  Letters + zero-padded chapter number (RSA PDF naming)."""
    m = re.match(r"^([A-Za-z]+)\s*-\s*(\d+)$", pid.strip())
    if not m:
        # allow already-normalized forms: T6, T06, T-6
        m2 = re.match(r"^([A-Za-z]+)(\d+)$", pid.strip())
        if not m2:
            raise ValueError(f"ab_law: cannot parse statute id '{pid}' (expected like T-6)")
        return (m2.group(1) + m2.group(2).zfill(2)).upper()
    return (m.group(1) + m.group(2).zfill(2)).upper()


def cache_pdf(code: str) -> Path:
    d = hermes_home() / "plugin-data" / "ca-law" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"ab-{code}.pdf"


def fetch_pdf(code: str) -> Path:
    url = f"{BASE}/{code}.pdf"
    cp = cache_pdf(code)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            blob = r.read()
    except Exception as e:
        if cp.exists():
            print(f"ab-law: network error ({e}); serving cached copy.", file=sys.stderr)
            return cp
        print(f"ab-law: network error fetching {url}: {e}", file=sys.stderr)
        sys.exit(2)
    if not blob.startswith(b"%PDF"):
        print(f"ab-law: {url} did not return a PDF (got {len(blob)} byte(s)).", file=sys.stderr)
        sys.exit(2)
    cp.write_bytes(blob)
    return cp


def to_text(pdf_path: Path, code: str) -> str:
    try:
        import tempfile
        fd, txt = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        r = subprocess.run(["pdftotext", "-layout", str(pdf_path), txt],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"ab-law: pdftotext failed: {r.stderr}", file=sys.stderr)
            sys.exit(2)
        raw = Path(txt).read_text(encoding="utf-8", errors="replace")
        os.unlink(txt)
        return raw
    except FileNotFoundError:
        print("ab-law: pdftotext not found (install poppler-utils).", file=sys.stderr)
        sys.exit(2)


# ---- body text cleaning ---------------------------------------------------
FTR = re.compile(r"^\s*(?:RSA\s+)?\d{4}\s+c[A-Za-z0-9.\-]+\.?\s+\d*\s*s\d")  # history footer (starts at line's left)
RUN_HDR = re.compile(r"Section\s+[\d.]+\s+.*(?:ACT)\s+Chapter\s+[A-Z]", re.I)
PNUM = re.compile(r"^\s*\d{1,3}\s*$")
RSA = re.compile(r"^\s*RSA\s*\d{4}\s*$")
ACTHEAD = re.compile(r"^\s*[A-Z ]*\bACT\b.*Chapter\s")
ENACTS = re.compile(r"enacts as follows:")


def lines_of(raw: str) -> list[str]:
    return raw.split("\n")


def is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if RUN_HDR.search(line) or RSA.match(line) or PNUM.match(line):
        return True
    # running act header alone across page breaks
    if ACTHEAD.search(line) and "(" not in line and "Chapter" in line and "Section" not in line:
        return True
    return False


def find_blocks(lines: list[str]) -> list[list[int]]:
    """Return list of [start, end] line-index ranges (end inclusive) that delimit
    logical chunks bounded by history footers (a footer ends the prior chunk)."""
    ends_footer: list[int] = []
    for i, ln in enumerate(lines):
        if FTR.search(ln):
            ends_footer.append(i)
    # first chunk starts after the enacting clause
    start = 0
    for i, ln in enumerate(lines):
        if ENACTS.search(ln):
            start = i + 1
            break
    blocks: list[list[int]] = []
    prev = start
    for ef in ends_footer:
        if ef >= prev:
            blocks.append([prev, ef])
            prev = ef + 1
    # residual tail after last footer
    if prev < len(lines):
        blocks.append([prev, len(lines) - 1])
    return blocks


def section_start_at(lines: list[str], i: int, sec: str) -> bool:
    m = re.match(rf"^\s*{re.escape(sec)}\((\d+)?\)", lines[i])
    if m:
        return True
    # decimal sections like "1.1 Subject to ..." or "18.1  Regulations"
    m2 = re.match(rf"^\s*{re.escape(sec)}\s+(.+)", lines[i])
    return bool(m2)


def extract_section(raw: str, sec: str) -> str | None:
    lines = lines_of(raw)
    blocks = find_blocks(lines)
    for b in blocks:
        lo, hi = b[0], b[1]
        hit = None
        for i in range(lo, hi + 1):
            if section_start_at(lines, i, sec):
                hit = i
                break
        if hit is None:
            continue
        # collect body from hit..hi, stripping noise, keeping history footer line out
        body: list[str] = []
        for ln in lines[hit:hi + 1]:
            if is_noise(ln):
                continue
            if FTR.search(ln):
                continue
            t = ln.rstrip()
            if t.strip():
                body.append(t)
        # drop a trailing shortline that is a page break orphan
        text = "\n".join(body).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Alberta statute lookup (King's Printer PDF)")
    ap.add_argument("pid", help="RSA chapter id, e.g. T-6")
    ap.add_argument("args", nargs="*", help="section number / --search")
    ap.add_argument("--search", "-s", metavar="WORD", help="search sections for WORD")
    a = ap.parse_args()

    try:
        code = chapter_to_code(a.pid)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    pdf = fetch_pdf(code)
    raw = to_text(pdf, code)

    # top-of-document title / citation line
    cite_line = "Traffic Safety Act"
    m = re.search(r"\n\s*([A-Z][A-Z'\- ]+ACT)\s*\nRevised Statutes of Alberta\s*\n\s*Chapter\s+([A-Z]\d[\d.]*)\s*\n\s*Current as of ([^\n]+)", raw)
    edition = ""
    if m:
        cite_line = m.group(1).strip()
        edition = m.group(3).strip()

    if a.search:
        needle = a.search.lower()
        lines = lines_of(raw)
        hits = []
        for i, ln in enumerate(lines):
            if is_noise(ln) or FTR.search(ln):
                continue
            low = ln.lower()
            if needle in low:
                # find containing section number
                s = re.match(r"^\s*([\d.]+)\s*(\()?", lines[i-1])
                sec = re.match(r"^\s*([\d.]+)\s*\(", ln)
                num = (sec or s).group(1) if (sec or s) else "?"
                hits.append((num, ln.strip()))
        if not hits:
            print(f"ab-law: no match for '{a.search}' in {a.pid.upper()}.")
            return 1
        print(f"Matches for '{a.search}' in {a.pid.upper()} (first 20):\n")
        seen = set()
        for num, ln in hits[:40]:
            key = (num, ln)
            if key in seen:
                continue
            seen.add(key)
            print(f"[s.{num}] {ln[:150]}")
        print(f"\n-- {len(seen)} match(es).")
        return 0

    sec = re.sub(r"[^\d.]", "", " ".join(a.args))
    if not sec:
        print(f"ab-law: provide a section number, e.g. {a.pid} 1", file=sys.stderr)
        return 1

    text = extract_section(raw, sec)
    if text is None:
        print(f"ab-law: section {sec} not found in {a.pid.upper()} (chapter {code}).", file=sys.stderr)
        return 1

    print(text)
    print("")
    print(f"(s. {sec} {a.pid.upper()}, {cite_line}, RSA 2000 c {a.pid}; "
          f"Alberta King's Printer office consolidation"
          + (f", current to {edition}" if edition else "")
          + f" — {BASE}/{code}.pdf, retrieved {date.today().isoformat()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
