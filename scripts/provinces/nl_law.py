#!/usr/bin/env python3
"""
nl_law.py - Fetch a Newfoundland and Labrador provincial statute section verbatim
from the official House of Assembly legislation site.

Usage:
    python3 nl_law.py <statute-id> <section>
    python3 nl_law.py L-18 1

Example URL built: https://www.assembly.nl.ca/Legislation/sr/statutes/l18.htm
"""
import sys
import re
import html
import datetime
import urllib.request

BASE = "https://www.assembly.nl.ca/Legislation/sr/statutes/{}.htm"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def norm_id(statute_id):
    """L-18 -> l18 ; keep non-alnum removed, lowercase."""
    return re.sub(r"[^a-zA-Z0-9]", "", statute_id).lower()


def anchor_name(section):
    """'1' -> '1_'; '2.1' -> '2_1' (matches <A NAME=N_> anchors on the site)."""
    s = str(section)
    return s.replace(".", "_") + ("_" if "." not in s else "")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    # The official HTML is authored in windows-1252.
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\xa0", " ")
    return s


def clean_block(s):
    """Normalise whitespace for readable verbatim output."""
    s = s.replace("\r", " ")
    s = re.sub(r"[ \t]+", " ", s)  # collapse spaces/tabs
    lines = [re.sub(r"^ +", "", ln).rstrip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln.strip())


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    statute_id, section = sys.argv[1], sys.argv[2]

    url = BASE.format(norm_id(statute_id))
    page = fetch(url)

    anchor = "<A NAME=" + anchor_name(section) + ">"
    if anchor not in page:
        sys.exit("Section not found: anchor '%s' not present in %s" % (anchor, url))

    start = page.index(anchor) + len(anchor)
    # Section runs until the next section anchor.
    raw = page[start:]
    next_anchor = re.search(r"<A NAME=\d", raw)
    end = start + next_anchor.start() if next_anchor else len(page)
    block = page[start:end]

    # Strip the anchor's own closing tag and any leading "Back to Top" link
    # (present as leftover on subsection anchors like 2.1).
    block = re.sub(r"^</A>", "", block)
    block = re.sub(r"^\s*<p[^>]*>\s*<A HREF=#top>\s*Back to Top\s*</A>\s*</p>", "", block, flags=re.I)

    # Cut at the section's own trailing "Back to Top" link.
    bt = re.search(r">\s*Back to Top\s*</A>", block, re.I)
    if bt:
        block = block[:bt.start()]

    heading_m = re.search(r'class="Sidenote".*?<FONT SIZE="2">(.*?)</b>', block, re.S)
    body_m = re.search(r'<p class="Section">(.+?)<p class="RSN">', block, re.S)
    rsn_m = re.search(r'<p class="RSN">(<span[^>]*>)?(.*?)</span>?', block, re.S)

    heading = strip_tags(heading_m.group(1)) if heading_m else "(heading not found)"
    body = clean_block(strip_tags(body_m.group(1))) if body_m else clean_block(strip_tags(block))
    history = clean_block(strip_tags(rsn_m.group(1))) if rsn_m else ""

    citation = "RSNL1990 CHAPTER %s" % statute_id
    retrieved = datetime.date.today().strftime("%B %-d, %Y")

    print("=" * 70)
    print("HEADING:  %s" % heading)
    print("CITATION: %s" % citation)
    print("SECTION:  %s" % section)
    print("SOURCE:   %s" % url)
    print("RETRIEVED: %s" % retrieved)
    if history:
        print("HISTORY:  %s" % history)
    print("=" * 70)
    print(body)
    print("=" * 70)


if __name__ == "__main__":
    main()
