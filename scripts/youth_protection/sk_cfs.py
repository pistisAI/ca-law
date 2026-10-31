"""
SK The Child and Family Services Act (SS 1989-90, c C-7.2).
Source: publications.saskatchewan.ca
"""
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

def fetch() -> str:
    cache_file = CACHE_DIR / "sk_cfs.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    req = urllib.request.Request("https://publications.saskatchewan.ca/api/v1/products/23011/formats/29464/download", headers={"User-Agent": "ca-law/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    cache_file.write_text(html, encoding="utf-8")
    return html

def search(keyword: str) -> str:
    html = fetch()
    lines = [l for l in html.split("\n") if keyword.lower() in l.lower()]
    return "\n".join(lines[:20]) if lines else "No matches"

def get_section(section: str) -> str:
    return f"[STUB] SK CFS section {section} - implement proper parser"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SK CFS lookup")
    parser.add_argument("section", nargs="?", help="Section number")
    parser.add_argument("--search", "-s", help="Search keyword")
    args = parser.parse_args()
    if args.search:
        print(search(args.search))
    elif args.section:
        print(get_section(args.section))
    else:
        print("Usage: python -m ca_law.scripts.youth_protection.sk_cfs <section> | --search <keyword>")
