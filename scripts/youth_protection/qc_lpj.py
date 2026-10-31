"""
Québec Loi sur la protection de la jeunesse (LPJ, P-34.1) adapter.

Wraps qc_law.py for youth-protection-specific queries.
Source: legisquebec.gouv.qc.ca (official Légis Québec HTML).
"""
import subprocess
import sys
from pathlib import Path

QC_LAW = Path(__file__).parents[1] / "provinces" / "qc_law.py"

def get_article(article: str) -> str:
    """Fetch LPJ article verbatim via qc_law.py."""
    result = subprocess.run([sys.executable, str(QC_LAW), "P-34.1", article], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return f"Error fetching LPJ art. {article}: {result.stderr}"
    return result.stdout.strip()

def search(keyword: str) -> str:
    """Search LPJ for keyword."""
    result = subprocess.run([sys.executable, str(QC_LAW), "P-34.1", "--search", keyword], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return f"Error searching LPJ: {result.stderr}"
    return result.stdout.strip()

# Key articles verified this session
KEY_ARTICLES = {
    "2": "Object of the Act",
    "3": "Child's interest paramount",
    "38": "Compromise grounds (abandonment, neglect, psychological mistreatment, exposure to family violence, sexual/physical abuse, serious behavioral disorder)",
    "72": "Obstructing an inspector (NOT the 72h rule — that's a judgment provision, ¶93-94, NOT a statute article)",
}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LPJ youth protection article lookup")
    parser.add_argument("article", nargs="?", help="Article number (e.g., 38)")
    parser.add_argument("--search", "-s", help="Search keyword")
    args = parser.parse_args()
    if args.search:
        print(search(args.search))
    elif args.article:
        print(get_article(args.article))
    else:
        print("Usage: python -m ca_law.scripts.youth_protection.qc_lpj <article> | --search <keyword>")
        print("Key articles:", KEY_ARTICLES)
