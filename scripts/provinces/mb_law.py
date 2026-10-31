#!/usr/bin/env python3
"""
mb_law.py — Read a Manitoba consolidated provincial statute section VERBATIM
from the official Manitoba Laws site (https://web2.gov.mb.ca/laws/statutes/ccsm/).

Usage:
    python3 mb_law.py H60 1
    python3 mb_law.py <CCSM chapter id> <section>

The statute's consolidated text is an HTML page served at
    https://web2.gov.mb.ca/laws/statutes/ccsm/<lower-letter><3-digit>.php?lang=en
Each section is a <div class="regrow" id="N"> containing an English column
(<div class="regcol-e">) and a French column (<div class="regcol-f">).
Only the English column is printed.
"""
import sys
import re
import urllib.request
from html.parser import HTMLParser
from datetime import date

BASE = "https://web2.gov.mb.ca/laws/statutes/ccsm/"
INDEX = "https://web2.gov.mb.ca/laws/statutes/index_ccsm.php"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

# Level at which a tag starts a fresh text block in the English column.
BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
              "table", "tr", "td", "th", "blockquote"}


def chapter_to_path(chapter):
    m = re.match(r"^\s*([a-zA-Z])([0-9][0-9.]*)\s*$", chapter.strip())
    if not m:
        raise ValueError(f"Cannot parse CCSM chapter id: {chapter!r}")
    letter, num = m.group(1).lower(), m.group(2)
    lead = re.match(r"^\d+", num).group(0)
    return f"{letter}{lead.zfill(3)}{num[len(lead):]}.php"


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def find_official_path(chapter):
    try:
        data = fetch(INDEX)
    except Exception as e:
        raise RuntimeError(f"Could not fetch index to resolve chapter: {e}")
    key = re.sub(r"[^A-Z0-9]", "", chapter).upper()
    pat = re.compile(
        r'href="ccsm/([a-z0-9.]+\.php)\?lang=en"[^>]*>(?:<[^>]+>)*\s*'
        r'(?:[^<]*<[^>]+>)*?' + re.escape(key),
        re.DOTALL)
    m = pat.search(data)
    return m.group(1) if m else None


class SectionParser(HTMLParser):
    def __init__(self, section):
        super().__init__(convert_charrefs=True)
        self.section = str(section)
        self.stack = []          # open tags (div close tolerance)
        self.depth = 0           # current nesting depth
        self.in_target = False
        self.in_english = False
        self.e_row_depth = 0     # stack depth when target div.regrow opened
        self.e_col_depth = 0     # stack depth when regcol-e opened
        self.title = None
        self.heading = None
        self.blocks = []         # (is_heading, text)
        self.cur = None
        self.cur_is_heading = False
        self.title_buf = None

    def _att(self, attrs):
        d = {}
        for k, v in attrs:
            d[k.lower()] = v
        return d

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        a = self._att(attrs)
        cls = (a.get("class") or "").split()
        self.stack.append((tag, a, self.depth))

        if not self.in_target:
            if tag == "div" and a.get("id") == self.section and "regrow" in cls:
                self.in_target = True
                self.e_row_depth = self.depth
                self.cur = []
            elif tag == "h1" and "left" in cls and self.title is None:
                self.title_buf = []
            return

        if self.in_target and not self.in_english and \
                tag == "div" and "regcol-e" in cls:
            self.in_english = True
            self.e_col_depth = self.depth
            self.cur = []
            self.cur_is_heading = False
            return

        if self.in_english:
            is_heading = (tag == "h6" and "secheading" in cls)
            if tag in BLOCK_TAGS:
                self._finalize()
                self.cur = []
                self.cur_is_heading = is_heading
            elif self.cur is None:
                self.cur = []
                self.cur_is_heading = is_heading

    def handle_endtag(self, tag):
        # record title text
        if tag == "h1" and self.title_buf is not None:
            self.title = "".join(self.title_buf).strip().rstrip(",").strip()
            self.title_buf = None
        # body text flush handled via starttag of next block / finalize

        if self.stack and tag == self.stack[-1][0]:
            self.stack.pop()
            self.depth -= 1
            # closing a BLOCK inside english: finalize that block
            if self.in_english and tag in BLOCK_TAGS and tag != "div":
                self._finalize()
            # closing regcol-e column
            if self.in_english and tag == "div" and self.depth == self.e_col_depth - 1:
                self._finalize()
                self.in_english = False
            # closing target div.regrow
            if self.in_target and tag == "div" and self.depth == self.e_row_depth - 1:
                self._finalize()
                self.in_target = False

    def handle_startendtag(self, tag, attrs):
        # <br/> etc. — treat as text break
        if tag == "br" and self.in_english and self.cur is not None:
            self.cur.append("\n")
        self.depth += 1
        self.depth -= 1

    def handle_data(self, data):
        if self.in_english and self.cur is not None:
            self.cur.append(data)
        elif self.title_buf is not None:
            self.title_buf.append(data)

    def handle_entityref(self, name):
        pass  # convert_charrefs=True handles numeric/named entities

    def _finalize(self):
        if self.cur is not None:
            txt = "".join(self.cur)
            if txt.strip():
                self.blocks.append((self.cur_is_heading, txt))
                if self.cur_is_heading and self.heading is None:
                    self.heading = txt
        self.cur = None
        self.cur_is_heading = False


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 mb_law.py <CCSM chapter id> <section>", file=sys.stderr)
        print("  e.g.  python3 mb_law.py H60 1", file=sys.stderr)
        sys.exit(2)
    chapter, section = sys.argv[1], sys.argv[2]

    url = BASE + chapter_to_path(chapter)
    try:
        html_doc = fetch(url)
    except Exception as e:
        print(f"Direct fetch failed ({e}); resolving via index...", file=sys.stderr)
        official = find_official_path(chapter)
        if not official:
            raise SystemExit(f"Could not locate consolidated page for chapter {chapter}.")
        url = BASE + official
        html_doc = fetch(url)

    p = SectionParser(section)
    p.feed(html_doc)

    if not p.heading and not p.blocks:
        raise SystemExit(f"Section {section} of chapter {chapter} was not found on {url}")

    print("=" * 78)
    print(f"TITLE    : {p.title or '(not parsed)'}")
    print(f"CITATION : C.C.S.M. c. {chapter.upper()}")
    print(f"SECTION  : {section}")
    print(f"HEADING  : {section} — {p.heading}" if p.heading else f"HEADING  : Section {section}")
    print(f"SOURCE   : {url}")
    print(f"RETRIEVED: {date.today().isoformat()}")
    print("=" * 78)
    for is_heading, block in p.blocks:
        print(block)


if __name__ == "__main__":
    main()
