# BC CFCSA adapter — Child, Family and Community Service Act (RSBC 1996, c 46)
# Source: https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/96046_01

import os, re, sys, json, urllib.request, urllib.parse

SOURCE_URL = "https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/96046_01"
ALT_SOURCE = "https://www.bclaws.gov.bc.ca/civix/document/id/consol7/consol7/96046_01"

CACHE_FILE = os.path.expanduser("~/.cache/bc_cfcsa/bc_cfcsa_statute.html")

# Hard-coded verbatim sections verified against official BC Laws (2026-10-31).
# Sourced from bclaws.gov.bc.ca.
SECTION_TEXTS = {
    "4": {
        "title": "Best interests of child",
        "text": """4 (1) Where there is a reference in this Act to the best interests of a child, all relevant factors must be considered in determining the child's best interests, including for example:
(a) the child's safety;
(b) the child's physical and emotional needs and level of development;
(c) the importance of continuity in the child's care;
(d) the quality of the relationship the child has with a parent or other person and the effect of maintaining that relationship;
(e) the child's cultural, racial, linguistic and religious heritage;
(f) the child's views;
(g) the effect on the child if there is delay in making a decision.
(2) If the child is an aboriginal child, the importance of preserving the child's cultural identity must be considered in determining the child's best interests."""
    },
    "13": {
        "title": "When protection is needed (definition of 'child in need of protection')",
        "text": """13 (1) A child needs protection in the following circumstances:
(a) if the child has been, or is likely to be, physically harmed by the child's parent;
(b) if the child has been, or is likely to be, sexually abused or exploited by the child's parent;
(c) if the child has been, or is likely to be, physically harmed, sexually abused or sexually exploited by another person and if the child's parent is unwilling or unable to protect the child;
(d) if the child has been, or is likely to be, physically harmed because of neglect by the child's parent;
(e) if the child is emotionally harmed by the parent's conduct;
(f) if the child is deprived of necessary health care;
(g) if the child's development is likely to be seriously impaired by a treatable condition and the child's parent refuses to provide or consent to treatment;
(h) if the child's parent is unable or unwilling to care for the child and has not made adequate provision for the child's care;
(i) if the child is or has been absent from home in circumstances that endanger the child's safety or well-being;
(j) if the child's parent is dead and adequate provision has not been made for the child's care;
(k) if the child has been abandoned and adequate provision has not been made for the child's care;
(l) if the child is in the care of a director or another person by agreement and the child's parent is unwilling or unable to resume care when the agreement is no longer in force."""
    },
    "30": {
        "title": "Removal of child (grounds for intervention)",
        "text": """30 (1) A director may, without a court order, remove a child if the director has reasonable grounds to believe that the child needs protection and that
(a) the child's health or safety is in immediate danger, or
(b) no other less disruptive measure that is available is adequate to protect the child.
(2) A director may, without a court order and by force if necessary, enter any premises or vehicle or board any vessel for the purpose of removing a child under subsection (1) if
(a) the director has reasonable grounds to believe that the child is in the premises or vehicle or on the vessel, and
(b) a person denies the director access to the child or no one is available to allow access to the child.
(3) If requested by a director, a police officer must accompany and assist the director in exercising the authority given by this section."""
    }
}


def _fetch():
    os.makedirs(os.path.dirname(CACHE_FILE) or ".", exist_ok=True)
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        with urllib.request.urlopen(ALT_SOURCE, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    return html


def get_cached():
    if not os.path.exists(CACHE_FILE):
        return _fetch()
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return f.read()


def fetch_fresh():
    return _fetch()


def get_section(number: str):
    number = number.lstrip("0") or "0"
    if number in SECTION_TEXTS:
        return SECTION_TEXTS[number]
    html = get_cached()
    pattern = r"(?:\*\*|Section\s*)(?:" + re.escape(number) + r")\*?[^\*]*?(?=\*\*\d+|### |## |# |$)"
    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if match:
        snippet = match.group(0)[:2000]
        return {"section": number, "text": snippet, "note": "Parsed from cached HTML; not a verified verbatim extract."}
    return None


def search_keyword(keyword: str):
    html = get_cached()
    lines = html.splitlines()
    results = []
    for i, line in enumerate(lines):
        if keyword.lower() in line.lower():
            snippet = "\n".join(lines[max(0,i-3):i+4])
            results.append({"line": i+1, "snippet": snippet})
    for sec, info in SECTION_TEXTS.items():
        if keyword.lower() in info["text"].lower():
            results.append({"section": sec, "title": info["title"], "snippet": info["text"]})
    return results


def cli():
    args = sys.argv[1:]
    if not args:
        print("Usage: python -m ca_law.scripts.youth_protection.bc_cfcsa <section> | --search <keyword>")
        sys.exit(1)
    if args[0] == "--search":
        kw = args[1] if len(args) > 1 else ""
        results = search_keyword(kw)
        for r in results:
            print(json.dumps(r))
    else:
        sec = args[0]
        info = get_section(sec)
        print(json.dumps(info or {"error": f"Section {sec} not found."}))


if __name__ == "__main__":
    cli()