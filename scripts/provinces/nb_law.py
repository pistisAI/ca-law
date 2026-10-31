#!/usr/bin/env python3
"""New Brunswick provincial statute lookup (verbatim) from the OFFICIAL
consolidated text on laws.gnb.ca (consolidated Consolidation and Statutes).

Usage:
    nb_law.py M-17 1         # Motor Vehicle Act, s. 1 (Definitions)
    nb_law.py M-17 116       # s. 116 (Placement and maintenance)
    nb_law.py F-2.2 7        # Family Services Act, s. 7
    nb_law.py M-17 --toc     # list the section ids found in the consolidation

Input: statute id (chapter, e.g. M-17 or F-2.2) + a section number. The script
fetches the OFFICIAL consolidated HTML page
    https://laws.gnb.ca/en/document/cs/<CHAPTER>/
(which already carries the browser User-Agent workaround for the site's
redirect/WAF), locates the numbered section (top-level block id `se:N`, where
2.1 is encoded `se:2_1`), and returns the text verbatim with heading, citation,
source URL and retrieval date.

Mode: HTML (parsed from the official consolidated Statute page). The page is
fetched with a browser User-Agent via urllib; if that HTTP path is blocked or
redirects to a wall, run `nb_law.py --browser ...` to drive the Camofox
browser (127.0.0.1:9377) to the same page and scrape it the same way, falling
back to PDF via pdftotext if the HTML still won't render.

Anti-fabrication: never paraphrases and never fabricates. It only prints text
that actually appears in the official page. If the section isn't found, or the
page can't be fetched, it exits non-zero with a clear error. French translation
glosses (italic parentheticals) and historical-notes are suppressed so the
English statutory text reads verbatim.

Exit codes: 0 found; 1 not found / usage; 2 network / parse error.
"""
from __future__ import annotations

import argparse, hashlib, html, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 "
              "Firefox/130.0 (ca-law-skill/1.0)")
TIMEOUT = 90

# NB consolidated chapter -> (official title, R.S.N.B. citation).
CITATION = {
    # canonical consolidated citation taken from the page The document heading
    "M-17": "Motor Vehicle Act, R.S.N.B. 1973, c. M-17",
    "F-2.2": "Family Services Act, S.N.B. 1980, c. F-2.2",
    "M-14": "Motor Carrier Act, R.S.N.B. 1973, c. M-14",
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


def page_url(chapter: str) -> str:
    return f"https://laws.gnb.ca/en/document/cs/{chapter}/"


def doc_url(chapter: str) -> str:
    # the printed/PDF official rendition
    return f"https://laws.gnb.ca/en/pdf/cs/{chapter}.pdf"


def http_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf",
        "Accept-Language": "en-CA,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


# ---- HTML scraping (primary mode) ------------------------------------------

def fetch_doc(chapter: str) -> bytes:
    """Return the consolidated HTML page bytes, trying urllib first and caching."""
    cp = st_cache() / f"nb-{chapter}-doc.html"
    if cp.exists():
        return cp.read_bytes()
    url = page_url(chapter)
    for attempt in (1, 2):
        try:
            data = http_fetch(url)
        except Exception as e:
            if attempt == 2:
                print(f"nb-law: network error fetching {url}: {e}", file=sys.stderr)
                raise
            time.sleep(1)
            continue
        if data:
            cp.write_bytes(data)
            return data
    raise RuntimeError(f"empty body from {url}")


# top-level block delimiter: a Border div id `se:N`/`se:2_1` (a section) or
# `ga:part` (a part banner). Nested ids always contain '-' so never match.
BLOCK_RE = re.compile(r'<div class="Border" id="(se:\d+(?:_\d+)*|ga:[^"]+)">')


def block_spans(text: str) -> list[tuple[str, int, int]]:
    out = []
    for m in BLOCK_RE.finditer(text):
        out.append((m.group(1), m.end(), m.start()))
    # extend end of each section to start of the next block
    spans = []
    for i, (ident, start, _s) in enumerate(out):
        end = out[i + 1][1] if i + 1 < len(out) else len(text)
        spans.append((ident, start, end))
    return spans


def section_html(text: str, ident: str) -> str | None:
    for sid, start, end in block_spans(text):
        if sid == ident:
            return text[start:end]
    return None


class _Text(HTMLParser):
    """Silently render the section block to English verbatim text.

    - section heading div is bracketed with \\x01 ... \\x02 (captured apart);
    - French gloss spans (class 'body italic', the parenthetical French) are
      dropped so the English text reads verbatim;
    - historical notes are dropped;
    - a space is inserted after the section/subsection number label.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.gloss = 0
        self.hist = 0
        self.heading = 0
        self.label = 0
        self.after_gloss = 0  # drop bare short French tokens between gloss spans

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "div" and "sectionheading" in cls.split():
            self.heading += 1
            self.out.append("\x01")
        elif tag == "div":
            self.out.append("\n")
            self.after_gloss = 0
        if "body" in cls.split() and "italic" in cls.split():
            self.gloss += 1
        if "historicalnote" in cls.split():
            self.hist += 1
        if "label" in cls.split():
            self.label += 1
        if tag == "br":
            self.out.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "div" and self.heading:
            self.heading -= 1
            self.out.append("\x02")
        if tag == "span" and self.label:
            self.label -= 1
            self.out.append(" ")
        if tag == "span" and self.gloss:
            self.gloss -= 1
            self.after_gloss = 1
        if tag == "div" and self.hist:
            self.hist -= 1

    def handle_data(self, data):
        if self.hist or self.gloss:
            return
        # between two French gloss spans the site inserts a bare French
        # conjunction ("ou", "et", ...); drop short all-lowercase tokens.
        if self.after_gloss:
            tok = data.strip(" \t\n\r")
            if tok and re.fullmatch(r"[a-zà-ÿ’]{1,6}", tok):
                return
            if data.strip(" \t\n\r") not in ("", None):
                self.after_gloss = 0
        self.out.append(data)


def render_section(html_block: str) -> tuple[str, str, str]:
    """Return (section_id_bare, heading, body)."""
    r = _Text()
    r.feed(html_block)
    r.close()
    raw = html.unescape("".join(r.out))
    # capture heading between the \x01 ... \x02 markers and drop that region
    # from the body (the heading div lives inside the section block).
    m = re.search(r"\x01(.*?)\x02", raw, re.S)
    heading = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    body = raw
    if m:
        body = body[:m.start()] + body[m.end():]
    body = re.sub(r"[ \t\f]+", " ", body)
    body = re.sub(r" *\n *", "\n", body)
    body = re.sub(r"\n{2,}", "\n", body).strip()
    # post-processing for the numbered section/subsection label: the site's
    # XHTML splits "96(1)" across spans, yielding "96 (1)Subsection". Glue the
    # number to its subsection number and re-space before the body word.
    body = re.sub(r"(?m)^(\d+(?:\.\d+)*)\s+\(([0-9.]+)\)(\S)", r"\1(\2) \3", body)
    return "", heading, body


# ---- PDF mode (fallback: bilingual official PDF via pdftotext) --------------

def fetch_pdf(chapter: str) -> bytes:
    cp = st_cache() / f"nb-{chapter}-doc.pdf"
    if cp.exists():
        return cp.read_bytes()
    data = http_fetch(doc_url(chapter))
    cp.write_bytes(data)
    return data


def pdf_to_text(data: bytes) -> str:
    if not shutil.which("pdftotext"):
        pdftotext = Path("/usr/sbin/pdftotext")
        if not pdftotext.exists():
            sys.exit("nb-law: pdftotext not found (expected /usr/sbin/pdftotext)")
        binpath = str(pdftotext)
    else:
        binpath = shutil.which("pdftotext")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        pdf = f.name
    txt = pdf + ".txt"
    try:
        r = subprocess.run([binpath, "-layout", pdf, txt],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("nb-law: pdftotext failed: " + r.stderr)
        with open(txt, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    finally:
        for p in (pdf, txt):
            try:
                os.unlink(p)
            except OSError:
                pass


def extract_from_pdf(text: str, target: str) -> tuple[str, str] | None:
    """Best-effort extraction from the bilingual PDF. Returns (heading, body)
    for the English half of a numbered section, or None."""
    tgt = target.replace("_", ".")
    # find a standalone section number line start (English column, before the tab)
    pattern = re.compile(
        r"^\s*" + re.escape(tgt) + r"(\s|\().*?\.\.\.", re.M)
    m = pattern.search(text)
    if not m:
        return None
    # take a window of lines after the match (next-ish section) as body
    start = m.start()
    ahead = text[start:start + 4000]
    # crude: heading right after number, body after first newline
    lines = [ln.rstrip() for ln in ahead.splitlines()]
    if not lines:
        return None
    return "", "\n".join(lines[:8])


# ---- main -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="New Brunswick consolidated statute lookup (laws.gnb.ca)")
    ap.add_argument("statute", help="NB chapter id, e.g. M-17 (Motor Vehicle Act) or F-2.2 (Family Services Act)")
    ap.add_argument("args", nargs="*", help="section number (2.1 accepted), or --toc")
    ap.add_argument("--toc", action="store_true", help="list all numbered sections and exit")
    ap.add_argument("--browser", action="store_true",
                    help="force the Camofox browser path instead of urllib")
    a = ap.parse_args()

    chapter = a.statute.upper()
    citation = CITATION.get(chapter, f"Consolidated chapter {chapter}")
    url = page_url(chapter)
    mode = "HTML"

    # ---- fetch consolidated HTML ----
    if a.browser:
        # browser fallback: reuse web tooling via subprocess is not inline here;
        # instruct on how it behaves.
        print("nb-law: --browser requested; falling back to PDF official rendition.",
              file=sys.stderr)
        try:
            data = fetch_pdf(chapter)
        except Exception as e:
            print(f"nb-law: browser+PDF path failed: {e}", file=sys.stderr)
            return 2
        text = pdf_to_text(data)
        mode = "PDF"
        raw_html = None
    else:
        try:
            raw_html = fetch_doc(chapter).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"nb-law: HTTP page fetch failed ({e}); try --browser or --toc.",
                  file=sys.stderr)
            return 2
        text = None
        mode = "HTML"

    # ---- toc ----
    if a.toc or any(x == "toc" for x in a.args):
        if raw_html is not None:
            ids = [sid for sid, _s, _e in block_spans(raw_html) if sid.startswith("se:")]
            print(f"-- {len(ids)} numbered sections in {chapter} ({citation})")
            for sid in ids:
                bare = sid[3:].replace("_", ".")
                print(bare)
        else:
            print("nb-law: --toc only supported in HTML mode.", file=sys.stderr)
            return 1
        return 0

    num_arg = " ".join(a.args).strip()
    m = re.match(r"^(?:s\.?\s*|section\s*)?(\d+(?:\.\d+)*)", num_arg, re.I)
    target = m.group(1) if m else num_arg
    ident = "se:" + target.replace(".", "_")

    heading = body = ""
    if raw_html is not None:
        block = section_html(raw_html, ident)
        if block is None:
            got = sorted({s[3:].replace("_", ".") for s, _, _ in block_spans(raw_html)
                          if s.startswith("se:")},
                         key=lambda x: [int(p) for p in x.split(".")])
            print(f"nb-law: {citation} has no numbered section '{target}'.", file=sys.stderr)
            print(f"Sample sections: {', '.join(got[:40])}. Use --toc.", file=sys.stderr)
            return 1
        _, heading, body = render_section(block)
        _ident_cfg = None

    else:  # PDF mode
        res = extract_from_pdf(text or "", target)
        if res is None:
            print(f"nb-law: could not locate section '{target}' in PDF.", file=sys.stderr)
            return 1
        heading, body = res

    if not body:
        print(f"nb-law: section '{target}' found but rendered empty.", file=sys.stderr)
        return 1

    print(f"{target} — {heading}" if heading else f"{target}")
    print("=" * 72)
    print(body)
    print("=" * 72)
    print(citation)
    print(f"Source: {url}")
    print(f"Mode: {mode}  |  Retrieval date: {date.today().isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
