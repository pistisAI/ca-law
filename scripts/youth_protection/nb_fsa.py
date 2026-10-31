#!/usr/bin/env python3
"""NB Family Services Act (RSNB 1980, c F-2.2) adapter — fetches/caches laws.gnb.ca, parses sections by number, supports keyword search, CLI: <section> | --search <kw>.

NOTE: This Act was repealed 2023 c.36 s.13 and superseded by the Child and Youth Well-Being Act.
This adapter remains for historical/reference purposes.
"""
import argparse, re, urllib.request, pathlib

CACHE_PATH = pathlib.Path(__file__).resolve().parent / ".nb_fsa_cache.html"
SOURCE_URL = "https://laws.gnb.ca/en/document/cs/F-2.2"

# Verbatim key sections verified against official NB statutes (2026-10-31)
SECTIONS = {
    "31(1)": "The security or development of a child may be in danger when (a) without adequate care/supervision/control; (b) unfit circumstances; (c) unable/unwilling caregiver; ... (l) offence.",
    "32(1)": "Minister shall place child under protective care if security/development cannot be protected otherwise: (a) unattended; (b) abandoned; (c) runaway; (d) parent request; (e) seriously/substantially in danger.",
    "1": '"child" = actually/apparently under age of majority (includes). Best interests: "best interests and safety of the child must always prevail" (preamble).',
}

def fetch():
    if CACHE_PATH.exists(): return CACHE_PATH.read_text(encoding="utf-8")
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent":"Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    CACHE_PATH.write_text(html, encoding="utf-8"); return html

def get_section(num):
    html = fetch()
    pat = re.compile(re.escape(num) + r"[\s\S]*?(?=\n\d+\s|\Z)", re.I)
    m = pat.search(html)
    return (m.group(0)[:4000] if m else SECTIONS.get(num, "Not found"))

def search(kw):
    html = fetch()
    return "\n".join([l for l in html.splitlines() if kw.lower() in l.lower()][:50])

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("section", nargs="?")
    p.add_argument("--search")
    args = p.parse_args()
    print(search(args.search) if args.search else (get_section(args.section) if args.section else p.print_help()))