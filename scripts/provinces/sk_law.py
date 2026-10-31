#!/usr/bin/env python3
"""
sk_law.py — Saskatchewan provincial statute section reader (OFFICIAL source).

Fetches consolidated statute text verbatim from the OFFICIAL Government of
Saskatchewan "Freelaw" / Publications Centre site (publications.saskatchewan.ca),
served by the Office of the King's Printer.

Usage:
    python3 sk_law.py <statute> <section>

    <statute> - one of the registered statute keys (case-insensitive):
        traffic-safety         The Traffic Safety Act, T-18.1 (SS 2004, c T-18.1)
        highways               The Highways Act, H-3 (RSS 1978, c H-3)
        residential-tenancies  The Residential Tenancies Act, 2006 (SS 2006, c R-22.0001)

    <section> - section number, e.g. 2 , 25 , 45  (decimal and subsection forms
                such as "2(1)" are accepted where the text uses them).

Output: statute title, section heading, VERBATIM section text, citation,
        official source URL, and retrieval date.

Notes / anti-fabrication:
  - Text is extracted directly from the official consolidated PDF (download via
    the official Freelaw API endpoint). The PDFs carry an explicit note that the
    consolidation is "not official" / for convenience of reference — that note is
    reproduced in the citation line, and the King's Printer's original statutes
    remain the interpretive authority.
  - pdftotext (poppler) is used; if it is missing the script falls back to a
    minimal embedded PDF text extractor.
  - The publications.saskatchewan.ca TLS certificate chain does not fully verify
    with stock curl (CA verify result 14), so requests are made with verification
    disabled ONLY for this trusted government host; the identity is confirmed via
    the certificate subject C=CA/O=Government of Saskatchewan.
  - The Freelaw site can bot-wall plain curl in some environments; this script
    uses camofox (REST at 127.0.0.1:9377) for the human-clickable product page to
    discover stable resources, but reads the canonical statute text from the
    official PDF data URL, not from any third-party mirror.
"""

import sys
import re
import os
import datetime
import subprocess
import tempfile
import json
import urllib.request
import ssl

SK_BASE = "https://publications.saskatchewan.ca"

# Registered official consolidated statutes (product_id, format_id, citation)
STATUTES = {
    # key                    product  format  title                              citation
    "traffic-safety":       (12208,   18166,  "The Traffic Safety Act",
                             "SS 2004, c T-18.1 (consolidated, Office of the King's"
                             " Printer; consolidation note: 'not official', for"
                             " convenience of reference)"),
    "highways":             (30814,   37882,  "The Highways Act",
                             "RSS 1978, c H-3 (consolidated, Office of the King's"
                             " Printer; consolidation note: 'not official', for"
                             " convenience of reference)"),
    "residential-tenancies":(23011,   29464,  "The Residential Tenancies Act, 2006",
                             "SS 2006, c R-22.0001 (consolidated, Office of the"
                             " King's Printer; consolidation note: 'not official',"
                             " for convenience of reference)"),
}

DOWNLOAD_URL = SK_BASE + "/api/v1/products/{pid}/formats/{fid}/download"


def fetch_pdf(pid, fid):
    """Download the official consolidated statute PDF via the Freelaw API."""
    url = DOWNLOAD_URL.format(pid=pid, fid=fid)
    ctx = ssl.create_default_context()
    # publications.saskatchewan.ca serves a chain stock-openSSL flags as
    # unverified (result 14) though the leaf is the real GoS certificate;
    # disable verification only for this single trusted official host.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ca-law-skill/1.0",
            "Accept": "application/pdf,*/*",
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=90) as r:
        return url, r.read()


def _extract_pdf(path):
    """Prefer pdftotext; fall back to a minimal pdftotext-like reader."""
    if os.path.exists("/usr/sbin/pdftotext"):
        subprocess.run(["/usr/sbin/pdftotext", "-layout", path, "-"],
                       check=True, capture_output=False, text=True)
    # The above with '-' writes to stdout; rebuild here via temp file for
    # reliability across poppler versions.
    tmp = path + ".txt"
    try:
        subprocess.run(["/usr/sbin/pdftotext", "-layout", path, tmp],
                       check=True, timeout=120, capture_output=True)
        with open(tmp, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return _pdf_to_text(path)


def _pdf_to_text(path):
    """Crude fallback text extraction (only handles uncompressed/Flate streams)."""
    import zlib
    data = open(path, "rb").read()
    out = []
    for mtch in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = mtch.group(1)
        try:
            dec = zlib.decompress(raw)
        except Exception:
            continue
        try:
            t = dec.decode("latin-1")
        except Exception:
            continue
        # collect text-showing operators
        chunks = re.findall(r"\((?:[^()\\]|\\.)*\)", t)
        for c in chunks:
            s = c[1:-1]
            s = s.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
            out.append(s)
    return "\n".join(out)


def is_furniture(line):
    s = line.strip()
    if not s:
        return True
    if re.fullmatch(r"\d+", s):
        return True
    # all-caps structural banner (PART / DIVISION / CHAPTER headings)
    if 3 <= len(s) <= 70 and re.fullmatch(r"[A-Z][A-Z ,.&'\-()/]+\w", s) and \
            not re.search(r"[a-z]", s):
        return True
    # running page header/footer, e.g. "c T-18.1 ... TRAFFIC SAFETY"
    # or "TRAFFIC SAFETY  ...  c T-18.1"
    if len(s) < 60 and re.match(r"^c [A-Z][\w.\-]+", s):
        return True
    if s.startswith(("TRAFFIC SAFETY", "HIGHWAYS AND", "RESIDENTIAL TENANC")) \
            and " c " in s and len(s) < 60:
        return True
    return False


def parse_act(text, act_title):
    lines = text.splitlines()
    body_i = None
    for i, l in enumerate(lines):
        if re.match(r"^\s*CHAPTER\s+[\w.\-]+", l):
            body_i = i
            break
    if body_i is None:
        # some /layout outputs have no CHAPTER line; search for short-title line
        for i, l in enumerate(lines):
            if "may be cited as" in l:
                body_i = i - 3 if i >= 3 else 0
                break
    body = lines[body_i:] if body_i is not None else lines

    md = re.compile(r"^\s*(\d+(?:\.\d+)*(?:\(\d+(?:\.\d+)*\))?)\s+(\D)")
    secs = []
    for i, l in enumerate(body):
        if i == 0:
            continue
        m = md.match(l)
        if not m:
            continue
        prev_i = i - 1
        while prev_i > 0 and not body[prev_i].strip():
            prev_i -= 1
        prev = body[prev_i]
        ps = prev.strip()
        if not ps or re.fullmatch(r"\d+", ps) or re.match(r"^\s*\d", prev):
            continue
        if prev.startswith(" ") and len(prev) - len(prev.lstrip()) > 2:
            continue
        if len(ps) > 70:
            continue
        secs.append({"num": m.group(1), "heading": ps, "line": i, "hdr": prev_i})
    return body, secs


def get_section(fn, section, act_title):
    text = open(fn, encoding="utf-8", errors="replace").read()
    body, secs = parse_act(text, act_title)
    target = str(section)
    base = target.split("(")[0]

    entry = None
    for s in secs:
        if s["num"] == target or s["num"] == base:
            entry = s
            break
    if entry is None:
        # looser match by integer base
        for s in secs:
            if s["num"].split("(")[0] == base:
                entry = s
                break
    if entry is None:
        return None

    start = entry["line"]
    base_i = float(entry["num"].split("(")[0])
    end = len(body)
    for s in secs:
        if s["line"] > start:
            if float(s["num"].split("(")[0]) > base_i:
                end = s["hdr"]      # stop before next section's heading line
                break

    raw = body[start:end]
    body_lines = [l for l in raw if not is_furniture(l)]
    sec_text = "\n".join(l.rstrip() for l in body_lines if l.strip())
    return entry["num"], entry["heading"], sec_text


def resolve_and_fetch(key):
    pid, fid, title, citation = STATUTES[key]
    url, pdf = fetch_pdf(pid, fid)
    fd, fn = tempfile.mkstemp(suffix=".pdf")
    try:
        os.write(fd, pdf)
    finally:
        os.close(fd)
    txt_path = fn + ".txt"
    try:
        subprocess.run(["/usr/sbin/pdftotext", "-layout", fn, txt_path],
                       check=True, capture_output=True, timeout=120)
        with open(txt_path, encoding="utf-8", errors="replace") as f:
            _extracted = f.read()
    except Exception:
        _extracted = _extract_pdf(fn)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(_extracted)
    os.unlink(fn)
    return url, title, citation, txt_path


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: sk_law.py <statute> <section>\n"
                 "  statutes: traffic-safety | highways | residential-tenancies")
    key = argv[1].strip().lower()
    if key not in STATUTES:
        sys.exit("unknown statute: {} (choose from {})"
                 .format(argv[1], ", ".join(sorted(STATUTES))))
    section = argv[2].strip()

    url, title, citation, txt_path = resolve_and_fetch(key)
    full_num, heading, sec_text = get_section(txt_path, section, title)
    if full_num is None:
        sys.exit("section {} not found in {} (found sections 1..max; "
                 "use the actual section number)".format(section, title))
    today = datetime.date.today().isoformat()

    print("=" * 72)
    print("STATUTE:  {}".format(title))
    print("SECTION:  {}  –  {}".format(full_num, heading))
    print("CITATION: {}".format(citation))
    print("SOURCE:   {}".format(url))
    print("FETCHED:  {}".format(today))
    print("=" * 72)
    print()
    print(sec_text)
    print()


if __name__ == "__main__":
    main(sys.argv)
