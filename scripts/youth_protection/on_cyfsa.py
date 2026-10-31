"""
Ontario Child, Youth and Family Services Act, 2017 (SO 2017, c 14, Sched 1).
Source: e-Laws Ontario (canlii.org or ontario.ca/laws).
"""
import re
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

def fetch_statute() -> str:
    """Fetch CYFSA from e-Laws."""
    url = "https://www.ontario.ca/laws/statute/17c14"
    cache_file = CACHE_DIR / "on_cyfsa.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": "ca-law/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8")
    cache_file.write_text(html, encoding="utf-8")
    return html

def get_section(html: str, section: str) -> str:
    """Extract a section from CYFSA HTML (stub - needs proper parsing)."""
    # e-Laws uses specific HTML structure; this is a stub
    return f"[STUB] ON CYFSA section {section} - implement proper e-Laws parser"

def search(keyword: str) -> str:
    html = fetch_statute()
    # simple text search in cached HTML
    lines = [l for l in html.split("\n") if keyword.lower() in l.lower()]
    return "\n".join(lines[:20]) if lines else "No matches"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ON CYFSA lookup")
    parser.add_argument("section", nargs="?", help="Section number")
    parser.add_argument("--search", "-s", help="Search keyword")
    args = parser.parse_args()
    if args.search:
        print(search(args.search))
    elif args.section:
        print(get_section(fetch_statute(), args.section))
    else:
        print("Usage: python -m ca_law.scripts.youth_protection.on_cyfsa <section> | --search <keyword>")
