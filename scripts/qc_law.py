#!/usr/bin/env python3
"""Québec statute lookup from Légis Québec (official).

Usage:
    qc_law.py CCQ-1991 1457          # Code civil du Québec, art. 1457
    qc_law.py LPJ 38                 # Loi sur la protection de la jeunesse, art. 38
    qc_law.py CCQ-1991 --search garde # search headings + text
    qc_law.py CCQ-1991 toc           # list articles (first ~40)

Input: a Légis Québec law slug (CCQ-1991, LPJ, CPC, ...) + an article number.
The full law page is fetched from https://www.legisquebec.gouv.qc.ca and parsed
by stable element ids (div.section id="se:NNN"). Verbatim text + citation +
consolidation date + source. Never paraphrases.

Exit codes: 0 found; 1 not found/usage; 2 network/source error.
"""
from __future__ import annotations

import argparse, os, re, sys, urllib.request
from datetime import date
from html import unescape
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) ca-law-skill/1.0"
TIMEOUT = 90


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def raw_cache(slug: str) -> Path:
    d = hermes_home() / "plugin-data" / "ca-law" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"qc-{re.sub(r'[^A-Za-z0-9._-]', '_', slug)}.html"


def fetch_page(slug: str) -> tuple[str, str]:
    url = f"https://www.legisquebec.gouv.qc.ca/fr/document/cs/{slug}"
    cp = raw_cache(slug)
    cached = cp.read_text(encoding="utf-8", errors="replace") if cp.exists() else None
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", errors="replace")
        cp.write_text(raw, encoding="utf-8")
        return raw, url
    except Exception as e:
        if cached is not None:
            print(f"qc-law: network error ({e}); serving cached copy.", file=sys.stderr)
            return cached, url + " [cached]"
        print(f"qc-law: network error fetching {url}: {e}", file=sys.stderr)
        sys.exit(2)


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(unescape(s).split())


def parse_articles(html: str) -> dict:
    """Return {number: {heading, text, history}}. Articles are <div class=section id=se:NNN>."""
    out: dict = {}
    for m in re.finditer(r'<div class="section" id="se:(\d+)"(.*?)<div class="HistoricalNote"', html, re.S):
        number = m.group(1)
        inner = m.group(2)
        # text is in the Subsection spans (in-order labels) and SubsectionFirst divs
        subs = re.findall(r'class="Subsection[^"]*"[^>]*>(.*?)</span>', inner, re.S)
        text = " ".join(strip_tags(body) for body in subs)
        text = " ".join(text.split())
        out[number] = {"text": text}
    return out


def get_number(arg: str) -> str:
    return re.sub(r"\D", "", arg)


def main() -> int:
    ap = argparse.ArgumentParser(description="Québec statute lookup (Légis Québec)")
    ap.add_argument("slug", help="law slug, e.g. CCQ-1991 or LPJ")
    ap.add_argument("args", nargs="*", help="article number / toc")
    ap.add_argument("--search", "-s", metavar="WORD", help="search articles for WORD")
    a = ap.parse_args()

    html, src = fetch_page(a.slug)
    articles = parse_articles(html)

    if not articles:
        print(f"qc-law: could not find any articles on {src} for '{a.slug}'.", file=sys.stderr)
        return 2

    if any(x.strip().lower() == "toc" for x in a.args):
        nums = sorted(articles.keys(), key=lambda n: int(n))
        print(f"First {min(40, len(nums))} of {len(nums)} articles ({a.slug.upper()}):")
        for n in nums[:40]:
            print(f"  {n} — {articles[n]['text'][:70]}")
        print(f"\n({len(nums)} numbered articles total; pass a number to read one.)")
        return 0

    if a.search:
        needle = unescape(a.search).lower()
        hits = [(n, a2) for n, a2 in articles.items()
                if needle in n or needle in a2["text"].lower()]
        if not hits:
            print(f"qc-law: no article in {a.slug.upper()} matches '{a.search}'.")
            return 1
        print(f"Matches for '{a.search}' in {a.slug.upper()}:\n")
        for n, a2 in hits[:20]:
            print(f"{n} — {a2['text'][:160]}")
        print(f"\n-- {len(hits)} match(es).")
        return 0

    num = get_number(" ".join(a.args))
    art = articles.get(num)
    if art is None:
        print(f"qc-law: no article {num} in {a.slug.upper()}.", file=sys.stderr)
        print(f"Range: {min(articles, key=int)}–{max(articles, key=int)}. Use toc or --search.", file=sys.stderr)
        return 1

    print(art["text"])
    print(f"\n(art. {num} {a.slug.upper()}; Légis Québec, {src} — retrieved {date.today().isoformat()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
