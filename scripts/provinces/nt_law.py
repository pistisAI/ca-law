#!/usr/bin/env python3
"""
nt_law.py -- Read a Northwest Territories territorial statute section verbatim
from the OFFICIAL consolidated legislation files served by the Department of
Justice (justice.gov.nt.ca).  Falls back to the official mirror on gnwt.ca
(legacy_justice files = identical PDFs) when justice.gov.nt.ca 504s, and to the
camofox browser REST API as a last resort.

Usage:
    python3 nt_law.py "Motor Vehicles Act" 5
    python3 nt_law.py "Children's Law Act" 5.1
    python3 nt_law.py mva 35.5
    python3 nt_law.py cla 1

Prints the section heading, the verbatim body text, the citation, the source
URL actually used, and the retrieval date.

Source of law:
  - Justice Dpt consolidated statutes PDFs (the authorised office consolidations).
  Chapter mapping known in the official files:
      Motor Vehicles Act        RSNWT 1988, c. M-16     -> motor-vehicles/motor-vehicles.a.pdf
      Children's Law Act        SNWT 1997, c. 14        -> childrens-law/childrens-law.a.pdf
"""

import io
import os
import re
import sys
import json
import shutil
import datetime
import subprocess
import urllib.request
import urllib.error
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Known statutes: key words to chapter id / official PDF path / citation.
# ---------------------------------------------------------------------------
RUNNING_HEADERS = {"MOTOR VEHICLES", "MOTOR VEHICLES ACT", "ACT", "CHILDREN'S LAW ACT",
                   "CHILDREN’S LAW ACT", "\ufb02"}

STATUTES = {
    "motor vehicles": {
        "html": "https://www.justice.gov.nt.ca/en/files/legislation/motor-vehicles/motor-vehicles.a.pdf",
        "mirror": "https://gnwt.ca/sites/default/files/legacy_justice/files/legislation/motor-vehicles/motor-vehicles.a.pdf",
        "path": "p/mva.pdf",
        "citation": "Motor Vehicles Act, R.S.N.W.T. 1988, c. M-16",
        "running": ["MOTOR VEHICLES", "ACT", "Lois de la"] ,
    },
    "children": {
        "html": "https://www.justice.gov.nt.ca/en/files/legislation/childrens-law/childrens-law.a.pdf",
        "mirror": "https://gnwt.ca/sites/default/files/legacy_justice/files/legislation/childrens-law/childrens-law.a.pdf",
        "path": "p/cla.pdf",
        "citation": "Children's Law Act, S.N.W.T. 1997, c. 14",
        "running": ["CHILDREN'S LAW ACT", "CHILDREN’S LAW ACT", "LOI SUR LE DROIT"],
    },
}

CAMOFOX = "http://127.0.0.1:9377"      # camofox browser REST (lasr-resort)
PDFTOTEXT = "/usr/sbin/pdftotext"        # poppler
APP = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"

EN_BODY_MIN, EN_BODY_MAX = 86.0, 310.0  # English body column x-range (pts, 612-wide page)
MARGIN_MAX = 88.0                        # margin headings live left of this


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def today():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d")


def fetch_bytes(url, timeout=45):
    """Download a file with a browser UA.  Raises on HTTP/network failure."""
    req = urllib.request.Request(url, headers={"User-Agent": APP, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def camofox_fetch(url, out_path):
    """Fetch a PDF through the camofox browser REST API (browser mode)."""
    userId = "nt_law"
    # open a tab on the PDF; camofox saves it as a download artifact
    with urllib.request.urlopen(urllib.request.Request(
            f"{CAMOFOX}/tabs",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"userId": userId, "sessionKey": "nwt",
                             "url": url, "trace": False}).encode()),
            timeout=60) as r:
        resp = json.load(r)
    tab = resp.get("tabId")
    if not tab:
        raise RuntimeError("camofox: no tabId")
    # pull downloads with data
    dl_url = f"{CAMOFOX}/tabs/{tab}/downloads?userId={userId}&includeData=true"
    with urllib.request.urlopen(dl_url, timeout=60) as r:
        dl = json.load(r)
    downloads = dl.get("downloads") or []
    for d in downloads:
        data = d.get("data")
        if not data:
            continue
        # camofox may wrap the PDF in a JSON envelope with base64
        import base64
        payload = data
        try:
            plain = json.loads(payload)
            payload = plain.get("data") or plain.get("base64") or payload
        except Exception:
            pass
        if isinstance(payload, str):
            # try base64 decode (strip JSON envelope if present)
            s = payload
            try:
                decoded = base64.b64decode(s, validate=True)
                if decoded.startswith(b"%PDF"):
                    with open(out_path, "wb") as f:
                        f.write(decoded)
                    return out_path
            except Exception:
                pass
            # raw (JSON-escaped) data
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(payload)
            return out_path
        else:
            with open(out_path, "wb") as f:
                f.write(payload)
            return out_path
    raise RuntimeError("camofox: no download data captured")


def get_pdf(stat, tmpdir):
    """Return (local_pdf_path, source_url, mode).  mode in {html, mirror, browser}."""
    pdf = os.path.join(tmpdir, stat["path"])
    os.makedirs(os.path.dirname(pdf), exist_ok=True)
    sources = [
        (stat["html"], "html"),
        (stat["mirror"], "mirror"),
    ]
    for url, mode in sources:
        for attempt in range(3):
            try:
                data = fetch_bytes(url)
            except Exception as e:
                if attempt == 2:
                    print(f"  [fetch] {url} failed: {e}", file=sys.stderr)
                continue
            if data.startswith(b"%PDF"):
                with open(pdf, "wb") as f:
                    f.write(data)
                return pdf, url, mode
            # transient HTML/interstitial -> retry
        # fallthrough to next source
    # 3) camofox browser
    try:
        camofox_fetch(stat["html"], pdf)
        return pdf, stat["html"], "browser"
    except Exception as e:
        print(f"  [fetch] camofox failed: {e}", file=sys.stderr)
    raise RuntimeError("could not obtain official PDF from any source")


def extract_words_xml(pdf_path):
    """Run pdftotext -bbox-layout, return per-(page,y) sorted word lists with x."""
    xml_f = pdf_path + ".xml"
    cmd = [PDFTOTEXT, "-bbox-layout", pdf_path, xml_f]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raw = open(xml_f, encoding="utf-8").read()
    pages = re.findall(r'<page width="[\d.]+" height="[\d.]+">(.*?)</page>', raw, re.S)
    result = []  # list of OrderedDict y-> list[(x,text)]
    for body in pages:
        words = re.findall(
            r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)</word>',
            body)
        lines = OrderedDict()
        for xmin, ymin, xmax, _, text in words:
            x, y = float(xmin), float(ymin)
            text = text.replace("&quot;", '"').replace("&apos;", "'").replace("&#39;", "'")
            text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            lines.setdefault(round(y, 1), []).append((x, text))
        result.append(lines)
    return result


def reconstruct_sections(pages, running_prefixes):
    """
    Walk pages top-to-bottom.  Build a list of 'lines': (y, margin_words, body_words).
    Body = English column (x in body range).  Margin = headings left of body.
    Returns list of (margin_text, body_text) per line in reading order.
    """
    out = []
    for pi, lines in enumerate(pages):
        for y, ws in sorted(lines.items()):
            # sort the enclosed (x,text) tuples by x, then take text by column
            srt = sorted(ws)
            margin = [t for x, t in srt if x < MARGIN_MAX]
            body = [t for x, t in srt if EN_BODY_MIN <= x < EN_BODY_MAX]
            margin_t = " ".join(margin)
            body_t = " ".join(body)
            # skip running page headers / page numbers
            bt_upper = body_t.strip().upper()
            if bt_upper in running_prefixes:
                continue
            # lone running-title fragment across two lines
            if bt_upper.startswith("MOTOR VEHICLES") and len(body_t) < 40:
                continue
            if bt_upper.startswith("ACT") and len(body_t) <= 3:
                continue
            # page number alone
            if margin_t == "" and re.fullmatch(r"\d{1,3}", body_t.strip()):
                continue
            out.append((margin_t, body_t))
    return out


def _sec_marker():
    """Match a REAL section-number line (number, optional .sub, then '.' then
    whitespace or '(').  Rejects TOC entries like '5.1 assisted reproduction'
    where the number is a page reference, not a dot-followed-by-space."""
    return re.compile(r"^(\d+(?:\.\d+)?)\.(?:\s|\()")


def find_section(lines, wanted):
    """
    wanted like '5', '5.1', '35.5'.  Locate the body line whose leading token is
    'wanted.' (the section number).  Return (margin, start_idx).
    """
    wanted = wanted.strip()
    marker = _sec_marker()
    for i, (margin, body) in enumerate(lines):
        m = marker.match(body)
        if m and m.group(1) == wanted:
            return margin, i
    return None, None


def collate_heading(lines, start_idx):
    """Rebuild the section heading from margin-column words around the section
    start line.  In NWT consolidations the heading is typeset in the left
    margin beside the section number; it wraps across several margin-only lines
    that interleave with the body lines.  We walk outward from the section
    start, collecting margin text on lines whose body is empty, but stop at the
    next subsection marker ('(2)' style) or section marker so we don't grab the
    next block's heading.  Returns the joined heading or '' if none found."""
    sub_marker = re.compile(r"^\(\d+\)")
    sec_marker = _sec_marker()

    def take_from(i):
        """Yield margin-only line index i if it belongs to this heading."""
        if lines[i][0] and not lines[i][1].strip():
            return True
        return False

    # ---- backward: margin lines immediately before the section start ----
    forward_parts = []
    backward_parts = []
    i = start_idx
    # margin exactly on the start line
    if lines[i][0] and not lines[i][1].strip():
        backward_parts.insert(0, lines[i][0])
    j = i
    while j > 0:
        if take_from(j - 1):
            backward_parts.insert(0, lines[j - 1][0])
            j -= 1
        else:
            break
    # ---- forward: margin lines after start, until subsection/section marker ----
    k = i
    while k + 1 < len(lines):
        nb = lines[k + 1][1]
        nm = lines[k + 1][0]
        # stop when a margin-only line is immediately followed by a subsection/
        # section marker body line (that margin belongs to the next block)
        if nm and not nb.strip() and k + 2 < len(lines):
            nb2 = lines[k + 2][1]
            if sub_marker.match(nb2) or sec_marker.match(nb2):
                break
        if sub_marker.match(nb) and k + 1 > i:
            break
        if sec_marker.match(nb) and k + 1 > i:
            break
        if nm and not nb.strip():
            forward_parts.append(nm)
            k += 1
        elif nb.strip():
            # body line between heading fragments: keep scanning for more margin
            k += 1
        else:
            break
    frag = backward_parts + forward_parts
    return " ".join(w for w in frag if w)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    want_stat = sys.argv[1].lower()
    section = sys.argv[2].strip()

    # Exact alias / phrase matching (no fuzzy single-letter matching).
    ALIASES = {
        "mva": "motor vehicles",
        "motor": "motor vehicles",
        "motor vehicle": "motor vehicles",
        "motor vehicles act": "motor vehicles",
        "vehicles": "motor vehicles",
        "cla": "children",
        "children": "children",
        "children's law": "children",
        "childrens law": "children",
        "children's law act": "children",
        "childrens law act": "children",
        "law act": "children",
    }
    key = ALIASES.get(want_stat)
    if key is None:
        norm = re.sub(r"[^a-z0-9 ]", "", want_stat)
        tok = norm.split()
        # match if every significant token is shared with a known name
        for k, cand in (("motor vehicles", "motor vehicles act rsnwt 1988 c m16"),
                        ("children", "children's law act snwt 1997 c14")):
            cnorm = re.sub(r"[^a-z0-9 ]", "", cand).split()
            if tok and all(t in cnorm for t in tok):
                key = k
                break
    if key is None:
        print(f"Unknown statute: {sys.argv[1]}", file=sys.stderr)
        print("Known: Motor Vehicles Act, Children's Law Act", file=sys.stderr)
        sys.exit(2)
    stat = STATUTES[key]

    tmpdir = os.path.join(os.environ.get("TMPDIR", "/tmp"), "nt_law")
    os.makedirs(tmpdir, exist_ok=True)

    pdf, src_url, mode = get_pdf(stat, tmpdir)
    pages = extract_words_xml(pdf)
    lines = reconstruct_sections(pages, set(stat["running"]))

    heading, idx = find_section(lines, section)
    if idx is None:
        print(f"Section {section} not found in {stat['citation']}", file=sys.stderr)
        sys.exit(3)
    heading = collate_heading(lines, idx)

    # collect body text from idx until next section-number line
    marker = _sec_marker()
    # editorial annotation footnote (amendment history), not enacted text
    HIST_NOTE = re.compile(
        r"^(?:SNWT|RSNWT)\s+\d{4}(\s*,\s*[0-9A-Za-z()\.\-,; ]+)*$"
        r"|^SI-\d+|^TR-\d+")
    HIST_INLINE = re.compile(
        r"\s+(?:SNWT|RSNWT)\s+\d{4},c\.\d+(?:\([^)]*\))?(?:,\s*s(?:\.|ections?)?\s*\d+[^.]*\.?)?\s*$")
    ALLCAPS_HEAD = re.compile(r"^(?:PART|DIVISION)\b|[A-Z][A-Z&'’\s]{3,}$")
    body_lines = []
    n = idx
    while n < len(lines):
        margin, body = lines[n]
        if n > idx and marker.match(body):
            break
        bt = body.strip()
        if not bt:
            # trailing footnote line flanked by blanks after last subsection
            n += 1
            continue
        if not body_lines and HIST_NOTE.match(bt):
            n += 1
            continue
        # strip an inline amendment-history note glued to the end of a line
        bt = HIST_INLINE.sub("", bt).rstrip()
        # stop before any all-caps Part/Division heading that starts a new block
        if body_lines and ALLCAPS_HEAD.match(bt) and not bt.endswith("."):
            break
        body_lines.append(bt)
        n += 1
        if n - idx > 400:
            break
    # drop trailing amendment-history footnote line(s) and trailing blanks
    while body_lines and (not body_lines[-1] or HIST_NOTE.match(body_lines[-1].strip())):
        body_lines.pop()

    if not heading.strip():
        heading = f"Section {section}"

    print("=" * 72)
    print(f"HEADING: {heading}")
    print("=" * 72)
    for bl in body_lines:
        print(bl)
    print("=" * 72)
    print(f"CITATION: {stat['citation']}")
    print(f"SOURCE MODE: {mode}")
    print(f"SOURCE URL: {src_url}")
    print(f"RETRIEVED: {today()}")


if __name__ == "__main__":
    main()
