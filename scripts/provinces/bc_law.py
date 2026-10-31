#!/usr/bin/env python3
"""bc_law.py - Read a BC provincial statute section VERBATIM from the official
BC Laws site (https://www.bclaws.gov.bc.ca/, civix document server).

Usage:
    python3 bc_law.py <statute_id> <section>   (e.g. python3 bc_law.py 96338_01 1)

The statute id is the consolidated HTML catalog id used by BC Laws in:
    /civix/document/id/complete/statreg/<statute_id>
For the Offence Act (RSBC 1996 c 338) that id is 96338_01.

Prints the exact section heading, the verbatim section text, the citation,
the source URL and the retrieval date.
"""
import re
import sys
import html
import time
import datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen

ROOT = "https://www.bclaws.gov.bc.ca"
BASE = ROOT + "/civix/document/id/complete/statreg/{sid}"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def fetch(url):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    })
    with urlopen(req, timeout=60) as r:
        data = r.read()
    # deal with gzip
    if data[:2] == b"\x1f\x8b":
        import gzip
        data = gzip.decompress(data)
    # civix pages are served with charset in the bytes; decode robustly
    for enc in ("utf-8", "utf-8-sig", "iso-8859-1"):
        try:
            return data.decode(enc), None
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace"), None


class TextExtract(HTMLParser):
    """Gather block text of heading + paragraphs, preserving paragraph breaks."""
    BLOCKS = {"p", "h4", "h5", "h6", "div", "li", "td", "br"}
    STANDALONE = {"section", "chapter", "part"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0  # depth of non-section content to ignore
        self.in_block = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip += 1
            return
        if tag in self.BLOCKS:
            self.in_block += 1
            self.parts.append("\n")
        elif tag in ("h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCKS:
            self.in_block = max(0, self.in_block - 1)
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip == 0:
            self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        # collapse each line's internal whitespace, drop empty lines
        out = []
        for ln in raw.split("\n"):
            ln = " ".join(ln.split())
            if ln:
                out.append(ln)
        return "\n".join(out)


def find_section(htm, num):
    """Return the raw inner slice (HTML) for section <num>."""
    # locate all section-div starts in document order
    starts = [m for m in re.finditer(r'<div\s+class="section"\s*>\s*<a\s+name="(section[0-9]+(?:\.\d+)?)"',
                                     htm)]
    target = None
    for idx, m in enumerate(starts):
        name = m.group(1)  # e.g. 'section1', 'section10.1'
        if name == "section" + num:
            end = starts[idx + 1].start() if idx + 1 < len(starts) else len(htm)
            target = htm[m.start():end]
            break
    return target


def extract_section(htm, num):
    """Return (heading, bodytext) for section num, or (None, None)."""
    chunk = find_section(htm, num)
    if chunk is None:
        return None, None
    # heading = <h4>...</h4> inside the section
    hm = re.search(r"<h4[^>]*>(.*?)</h4>", chunk, re.S)
    heading = ""
    if hm:
        # strip anchors/tags from the heading
        heading = html.unescape(re.sub(r"<[^>]+>", "", hm.group(1)))
        heading = " ".join(heading.split())
    parser = TextExtract()
    parser.feed(chunk)
    body = parser.text()
    return heading, body


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: python3 bc_law.py <statute_id> <section>\n")
        sys.stderr.write("  e.g. python3 bc_law.py 96338_01 1\n")
        return 2
    sid = sys.argv[1].strip()
    sec = sys.argv[2].strip()
    url = BASE.format(sid=sid)
    last_err = None
    for attempt in range(3):
        try:
            htm, last_err = fetch(url)
            break
        except Exception as e:  # network error / 404
            last_err = e
            time.sleep(2)
    else:
        sys.stderr.write("ERROR: could not fetch %s (%r)\n" % (url, last_err))
        return 1

    # --- citation from <div id="title"> ---
    til = re.search(r'<div\s+id="title">(.*?)</div>', htm, re.S)
    citation = ""
    if til:
        title_text = re.sub(r"<[^>]+>", " ", til.group(1))
        citation = " ".join(title_text.split()).strip()
    if not citation:
        tm = re.search(r"<title>(.*?)</title>", htm, re.S)
        citation = html.unescape(tm.group(1)).strip() if tm else ""

    heading, body = extract_section(htm, sec)
    if body is None:
        sys.stderr.write("Section '%s' not found in %s (id=%s)\n" % (sec, url, sid))
        return 1

    retr = datetime.date.today().isoformat()
    print("TITLE        : %s" % (citation.split("[RSBC")[0].strip() or citation))
    print("CITATION     : %s" % citation)
    print("SECTION      : %s" % sec)
    print("HEADING      : %s" % (heading or "(no heading)"))
    print("SOURCE URL   : %s" % url)
    print("RETRIEVED    : %s" % retr)
    print("----- TEXT -----")
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
