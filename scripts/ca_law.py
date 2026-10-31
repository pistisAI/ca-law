#!/usr/bin/env python3
"""Canadian federal statute lookup from Justice Canada (official).

Usage:
    ca_law.py C-46 266            # Criminal Code, s. 266 (also '266(1)' or 's 266')
    ca_law.py C-46 --search 265   # search all sections whose number/heading contains it
    ca_law.py C-46 --search wound # search headings + text
    ca_law.py C-46 toc            # list numbered headings + first 80 chars

Input: chapter (e.g. C-46) + a section number or search term. The full act XML
is fetched from https://laws.justice.gc.ca/eng/XML/<Chapter>.xml (the official
Justice Laws source). Returns verbatim text with citation + edition date +
source. Never paraphrases or fabricates.

Exit codes: 0 found; 1 not found/usage; 2 network/source error.
"""
from __future__ import annotations

import argparse, hashlib, os, re, sys, urllib.request
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) ca-law-skill/1.0"
BASE = "https://laws.justice.gc.ca/eng/XML"
TIMEOUT = 90

CHAPTERS = {
    "C-46": "Criminal Code (R.S.C., 1985, c. C-46)",
    "Y-1.5": "Youth Criminal Justice Act (S.C., 2002, c. 1)",
    "F-11": "Fitness and Amateur Sport Act (R.S.C., 1985, c. F-11)",
    "P-34": "Personal Information Protection and Electronic Documents Act (S.C., 2000, c. 5)",
    "L-6": "Lobbying Act (R.S.C., 1985, c. 44 (4th Supp.))",
}


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def raw_cache(chapter: str) -> Path:
    d = hermes_home() / "plugin-data" / "ca-law" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"raw-{re.sub(r'[^A-Za-z0-9._-]', '_', chapter)}.xml"


def fetch_xml(chapter: str) -> tuple[bytes, str]:
    """Return (xml_bytes, source_url). Reuses the on-disk raw file but always revalidates
    with the network; on network failure, serves the last cached copy if present."""
    url = f"{BASE}/{chapter}.xml"
    cp = raw_cache(chapter)
    cached = cp.read_bytes() if cp.exists() else None
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    try:
        import gzip, io
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        cp.write_bytes(raw)
        return raw, url
    except Exception as e:
        if cached is not None:
            print(f"ca-law: network error ({e}); serving cached copy.", file=sys.stderr)
            return cached, url + " [cached]"
        print(f"ca-law: network error fetching {url}: {e}", file=sys.stderr)
        sys.exit(2)


NS = {"lims": "http://justice.gc.ca/lims"}
LIMS = "http://justice.gc.ca/lims"


def _text(el) -> str:
    if el is None:
        return ""
    return " ".join(("".join(el.itertext())).split())


def parse_sections(root: ET.Element) -> tuple[dict, str, str]:
    """Return ({number: {heading, text, hist}}, pit_date, current_to). Walks every <Section>."""
    current_to = (root.get(f"{{{LIMS}}}current-date") or "")
    pit_date = (root.get(f"{{{LIMS}}}pit-date") or "")
    out: dict = {}
    for sec in root.iter("Section"):
        label_el = sec.find("Label")
        mn = sec.find("MarginalNote")
        label = _text(label_el) if label_el is not None else ""
        heading = _text(mn) if mn is not None else ""
        # text: top-level <Text>, then <Subsection> blocks in order, then <Paragraph> under each.
        parts = []
        top = sec.find("Text")
        if top is not None:
            parts.append(_text(top))
        for sub in sec.findall("Subsection"):
            sublabel = _text(sub.find("Label"))
            # depth-first over this subsection: Text + Paragraphs, preserving (a)(b) order
            subbits = []
            st = sub.find("Text")
            if st is None:
                # some subsections nest paragraphs directly under themselves
                for p in sub.findall("Paragraph"):
                    pl = p.find("Label")
                    pt = _text(p.find("Text"))
                    prefix = _text(pl) if pl is not None else ""
                    subbits.append(f"{prefix} {pt}" if prefix else pt)
            else:
                subbits.append(_text(st))
                for p in sub.findall("Paragraph"):
                    pl = p.find("Label")
                    pt = _text(p.find("Text"))
                    prefix = _text(pl) if pl is not None else ""
                    subbits.append(f"{prefix} {pt}" if prefix else pt)
            body_sub = " ".join(x for x in subbits if x)
            if sublabel:
                parts.append(f"({sublabel}) {body_sub}" if body_sub else f"({sublabel})")
            elif body_sub:
                parts.append(body_sub)
        paras = []
        for p in sec.findall("Paragraph"):
            pl = p.find("Label")
            paras.append((_text(pl) if pl is not None else "", _text(p.find("Text"))))
        hist = _text(sec.find("HistoricalNote/HistoricalNoteSubItem"))
        if paras:
            parts.append(" ".join(f"{l} {t}" if l else t for l, t in paras if t))
        body = " ".join(x for x in parts if x)
        if label:
            out[label] = {"heading": heading, "text": body.strip(), "history": hist or ""}
    return out, pit_date, current_to


def get_number(section_arg: str) -> str:
    s = section_arg.strip()
    # s. 266 / 266(1) / art. 266 -> 266
    m = re.match(r"^(?:s\.?\s*|art\.?\s*|section|article)?\s*(\d+(?:\.\d+)?(?:[a-z])?)", s, re.I)
    return m.group(1) if m else s


def main() -> int:
    ap = argparse.ArgumentParser(description="Canadian federal statute lookup (Justice Canada)")
    ap.add_argument("chapter", help="act chapter, e.g. C-46")
    ap.add_argument("args", nargs="*", help="section number / 's 266(1)' / 'toc'")
    ap.add_argument("--search", "-s", metavar="WORD", help="search sections for WORD")
    a = ap.parse_args()

    chapter = a.chapter.upper()
    raw, src = fetch_xml(chapter)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"ca-law: could not parse {src}: {e}", file=sys.stderr)
        return 2
    sections, pit_date, current_to = parse_sections(root)

    # toc mode lists headings
    if any(x.strip().lower() == "toc" for x in a.args):
        for num in sorted(sections.keys(), key=lambda n: [int(x) if x.isdigit() else 0 for x in re.findall(r'\d+', n)]):
            s = sections[num]
            print(f"{num:<8} {s['heading']}")
        print(f"\n-- {len(sections)} numbered sections, current to {current_to} ({CHAPTERS.get(chapter, chapter)})")
        return 0

    if a.search:
        needle = a.search.lower()
        hits = []
        for num, s in sections.items():
            if needle in num.lower() or needle in s["heading"].lower() or needle in s["text"].lower():
                hits.append((num, s))
        if not hits:
            print(f"ca-law: no section in {CHAPTERS.get(chapter, chapter)} matches '{a.search}'.")
            return 1
        print(f"Matches for '{a.search}' in {CHAPTERS.get(chapter, chapter)} (current to {current_to}):\n")
        for num, s in hits[:20]:
            print(f"{num} — {s['heading']} — {s['text'][:140]}")
        print(f"\n-- {len(hits)} match(es).")
        return 0

    # normal section lookup
    num = get_number(" ".join(a.args))
    s = sections.get(num)
    if s is None:
        # tolerate leading zeros off: '266' vs '0266'
        for k in sections:
            if str(int(k)) == num.lstrip("0"):
                s = sections[k]; num = k; break
    if s is None:
        got = sorted(sections.keys())[:40]
        print(f"ca-law: {CHAPTERS.get(chapter, chapter)} has no numbered section '{num}'.", file=sys.stderr)
        print(f"Sample sections: {', '.join(got)}. Use 'toc' or --search.", file=sys.stderr)
        return 1

    print(f"{num} — {s['heading']}\n")
    print(s["text"])
    print(f"({CHAPTERS.get(chapter, chapter)})\n"
          f"Consolidated as of {pit_date}, current to {current_to}; source: {src} (retrieved {date.today().isoformat()})")
    if s.get("history"):
        print(f"Legislative history: {s['history']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
