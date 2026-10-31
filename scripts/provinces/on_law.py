#!/usr/bin/env python3
"""Fetch a numbered section of an Ontario provincial statute verbatim from the
OFFICIAL Ontario e-Laws site (root https://www.ontario.ca/laws).

The e-Laws pages are JavaScript-rendered, but the underlying official JSON API
endpoint that the React app itself calls serves the full statute text. This
script uses that official API:
    https://www.ontario.ca/laws/api/v2/legislation/<lang>/doc-search/<type>/<code>

Usage:
    python3 on_law.py <statute_id> <section>
Example:
    python3 on_law.py 90c43 30

statute_id: the e-Laws legislation code, e.g. 90c43 = RSO 1990, c C.43
            (Courts of Justice Act). Both code-only and the fuller path are
            accepted.
section:    the section number, e.g. 30
"""
import sys
import re
import json
import datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen

API = "https://www.ontario.ca/laws/api/v2/legislation/{lang}/doc-search/{type}/{code}"
PAGE = "https://www.ontario.ca/laws/{type}/{code}"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def resolve_code(raw):
    # Accept 90c43, C.43, or a fuller form; strip non-alphanumerics, lowercase.
    code = re.sub(r"[^a-z0-9]", "", raw.lower()).lstrip("c")
    return code


class TextExtractor(HTMLParser):
    """Strip HTML tags, keep paragraphs/'tr' as line breaks, preserve entities."""

    PARAS = {"p", "div", "tr", "br", "li", "table"}
    STS = {"span", "a", "u", "b", "em", "i", "strong", "sub", "sup"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.pending_space = False

    def handle_starttag(self, tag, attrs):
        if tag in self.PARAS:
            self.parts.append("\n")
            self.pending_space = False

    def handle_endtag(self, tag):
        if tag in self.PARAS:
            self.parts.append("\n")
            self.pending_space = False

    def handle_data(self, data):
        s = re.sub(r"\s+", " ", data)
        if s.strip():
            # collapse spaces intelligently
            if self.parts and self.parts[-1].endswith(" ") or not self.parts:
                self.parts.append(s)
            else:
                self.parts.append(" " + s)

    def text(self):
        raw = "".join(self.parts)
        lines = [" ".join(l.split()) for l in raw.split("\n")]
        lines = [l for l in lines if l]
        return "\n".join(lines)


def extract_section(content, target, doc_title):
    """Return (heading, body, found) for the numbered section in the HTML."""
    if not isinstance(content, str):
        return None, None, False

    sec_re = re.compile(
        r'<p class="section">(?P<sec><a name="?([^">\s]+)"?>.*?<b>\s*'
        + re.escape(str(target)) + r"\s*</b>)(?P<body>.*?)(?=</p><p class=\"(section|headnote)\"|</p>\s*<p class=\"(section|headnote)\")",
        re.I | re.S,
    )
    # simpler: locate the <p class="section"> whose <b> begins with target number
    start_re = re.compile(
        r'<p class="section">(?P<anchor><a name="[^"]*"></a><b>\s*'
        + re.escape(str(target)) + r"\s*</b>)",
        re.I | re.S,
    )
    m = start_re.search(content)
    if not m:
        # also match when section number appears without anchor (rare)
        start_re2 = re.compile(
            r'<p class="section">(?P<anchor><b>\s*' + re.escape(str(target)) + r"\s*</b>)",
            re.I | re.S,
        )
        m = start_re2.search(content)
        if not m:
            return None, None, False
    start = m.start()
    # next section boundary: next <p class="section"><a name="..."><b>
    nxt = re.compile(r'<p class="section"><a name="[^"]*"></a><b>', re.I)
    after = nxt.search(content, start + len(m.group(0)))
    body_html = content[start:after.start() if after else len(content)]
    # Trim trailing amendment-history / footnotes block
    amd = re.compile(r'<p class="footnoteLeft[^"]*amend', re.I)
    amd_m = amd.search(body_html)
    if amd_m:
        body_html = body_html[:amd_m.start()]

    # heading = first <p class="headnote"> immediately preceding this section
    head_re = re.compile(r'<p class="headnote">(.*?)</p>', re.I | re.S)
    before = content[:start]
    head_matches = list(head_re.finditer(before))
    heading = None
    if head_matches:
        last = head_matches[-1]
        # ensure no other section p between headnote and our section
        if not re.search(r'<p class="section">', before[last.start():]):
            hx = TextExtractor()
            hx.feed(last.group(1))
            heading = hx.text().strip()

    tx = TextExtractor()
    tx.feed(body_html)
    body = tx.text().strip()
    return heading, body, True


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    raw_code, raw_section = sys.argv[1], sys.argv[2]
    code = resolve_code(raw_code)
    if raw_section.lower().startswith("s"):
        raw_section = raw_section[1:]
    target = int(re.sub(r"\D", "", raw_section) or 0)
    if target <= 0:
        print(f"Invalid section number: {raw_section!r}")
        sys.exit(2)

    # Determine type (statute vs regulation): assume statute unless id not found
    typ = "statute"

    # 1. Fetch the official JSON document
    url = API.format(lang="en", type=typ, code=code)
    raw = fetch(url)
    doc = json.loads(raw)
    if "content" not in doc or not doc.get("content"):
        print(f"No content found for {code}. Raw API response:")
        print(raw[:2000])
        sys.exit(1)

    title = doc.get("title") or doc.get("actTitle") or doc.get("shortTitle") or code
    date_from = doc.get("dateFrom", "")
    updated = doc.get("updatedAt", "")

    heading, body, found = extract_section(doc["content"], target, title)
    if not found:
        print(f"Section {target} not found in {code} (Courts of Justice Act?).")
        sys.exit(1)

    page_url = PAGE.format(type=typ, code=code)
    today = datetime.date.today().isoformat()

    print("=" * 72)
    print("STATUTE:  ", title)
    if heading:
        print("HEADING:  ", heading)
    print("SECTION:  ", str(target))
    print("=" * 72)
    print(body)
    print("=" * 72)
    print("CITATION: ", title + (f", s. {target}." if target else ""))
    print("CONSOLIDATION DATE (in force):", date_from)
    print("SOURCE URL:", page_url)
    print("RETRIEVED: ", today)


if __name__ == "__main__":
    main()
