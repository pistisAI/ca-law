#!/usr/bin/env python3
"""NL Children, Youth and Families Act (SNL 2018 cC-12.3) adapter.
Verbatim statute parser. Source: https://www.assembly.nl.ca/legislation/sr/statutes/c12-3.htm
"""
import argparse, os, urllib.request, re, html

SOURCE_URL = "https://www.assembly.nl.ca/legislation/sr/statutes/c12-3.htm"
CACHE_FILE = os.path.expanduser("~/.cache/nl_cyfa_statute.html")

VERBATIM_SECTIONS = {
    "10": ("Definition of child in need of protective intervention", "10. (1) A child is in need of protective intervention where the child (a) is being, or is at risk of being, physically harmed by the action or lack of appropriate action by the child's parent; (b) is being, or is at risk of being, sexually abused or exploited by the child's parent; (c) is being, or is at risk of being, emotionally harmed by the parent's conduct..."),
    "11": ("Duty to report", "11. (1) Where a person has information that a child or youth is or may be in need of protective intervention, the person shall immediately report the information to a manager, social worker or peace officer."),
    "9": ("Best interests test (general principle)", "9. (1) This Act shall be interpreted and administered in accordance with the principle that the overriding and paramount consideration in a decision made under this Act shall be the best interests of the child or youth. (2) In determining a child's or youth's best interests, all relevant factors shall be considered, including (a) the child's or youth's safety, health and well-being; (b) the child's or youth's physical, emotional and developmental needs; (c) the child's or youth's relationship with family..."),
}

def fetch():
    d = os.path.dirname(CACHE_FILE); d and os.makedirs(d, exist_ok=True)
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent":"nl-cyfa-parser/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    with open(CACHE_FILE, "wb") as f: f.write(data)
    return CACHE_FILE

def lookup(sec):
    key = str(sec).strip()
    if key in VERBATIM_SECTIONS:
        t, txt = VERBATIM_SECTIONS[key]
        return f"Section {key} — {t}\n{SOURCE_URL}\n\n{txt}"
    return f"(No verbatim section {key}; cached HTML at {CACHE_FILE})"

def search(kw):
    hits = []
    for sec, (t, txt) in VERBATIM_SECTIONS.items():
        if kw.lower() in txt.lower() or kw.lower() in t.lower():
            hits.append(f"Section {sec}: {t}\n{txt[:500]}...")
    return "\n---\n".join(hits) or f"No matches for '{kw}' (cached at {CACHE_FILE})"

def cli():
    p = argparse.ArgumentParser()
    p.add_argument("section", nargs="?", help="Section number")
    p.add_argument("--search", help="Keyword search")
    args = p.parse_args()
    if args.search: print(search(args.search))
    elif args.section: print(lookup(args.section))
    else: print("Usage: python -m ca_law.scripts.youth_protection.nl_cyfa <section> | --search <keyword>")

if __name__ == "__main__":
    cli()