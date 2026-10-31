"""PEI Child Protection Act (RSPEI 1988, c C-5.1) adapter.
Sources:
- https://www.princeedwardisland.ca/sites/default/files/legislation/c-05-1-child_protection_act.pdf (official consolidation, current to Sept 9/24)
- https://cwrp.ca/sites/default/files/publications/en/PEI_Child_Protection_Act.pdf (reference consolidation with full section text)
Note: The original Act was repealed by 2023,c.17,s.78.1 (Sept 9/24) and replaced by the Child, Youth and Family Services Act (C-6.01).
This adapter preserves verbatim text from the repealed statute for reference/comparison purposes.
"""
import argparse, os, sys, re, urllib.request

PDF_URL = "https://www.princeedwardisland.ca/sites/default/files/legislation/c-05-1-child_protection_act.pdf"
FULL_REF_URL = "https://cwrp.ca/sites/default/files/publications/en/PEI_Child_Protection_Act.pdf"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "pei_cpa.pdf")
TEXT_CACHE = os.path.join(os.path.dirname(__file__), "pei_cpa_text.txt")

# Verbatim key sections (from reference consolidation)
VERBATIM = {
    "9": {
        "title": "Child in need of protection",
        "text": """CHILD IN NEED OF PROTECTION
9. A child is in need of protection where
(a) the child has suffered physical harm inflicted by a parent;
(b) the child is at substantial risk of suffering physical harm inflicted by a parent;
(c) the child has suffered harm caused by
(i) neglect of the child by a parent,
(ii) failure of a parent to adequately supervise or protect the child, or
(iii) failure of a parent to provide for the adequate supervision or protection of the child;
(d) the child is at substantial risk of suffering harm caused by
(i) neglect of the child by a parent,
(ii) failure of a parent to adequately supervise or protect the child, or
(iii) failure of a parent to provide for the adequate supervision or protection of the child;
(e) the child has been sexually abused by a parent or by another person where the parent knew or ought to have known of the possibility of sexual abuse of the child and the parent failed to protect the child;
(f) the child is at substantial risk of sexual abuse by a parent or by another person where the parent knew or ought to have known of the possibility of sexual abuse of the child and the parent failed to protect the child;
(g) the child has been harmed as a result of being sexually exploited for the purpose of prostitution and the parent has failed or been unable to protect the child;
(h) the child is at substantial risk of being sexually exploited for the purpose of prostitution and the parent has failed or been unable to protect the child;
(i) the child has been harmed as a result of being exposed to or involved in the production of child pornography and the parent has failed or been unable to protect the child;
(j) the child is at substantial risk of being harmed as a result of being exposed to or involved in the production of child pornography and the parent has failed or been unable to protect the child;
(k) the child has suffered emotional harm inflicted by a parent, or by another person, where the parent knew or ought to have known that the other person was emotionally abusing the child and the parent failed to protect the child;
(l) the child is at substantial risk of suffering emotional harm caused by a parent, or by another person, where the parent knew or ought to have known, that the other person was emotionally abusing the child and the parent failed to protect the child;
(m) the child has suffered physical or emotional harm caused by being exposed to domestic violence by or towards a parent;
(n) the child is at substantial risk of suffering physical or emotional harm caused by being exposed to domestic violence by or towards a parent;"""
    },
    "2(2)": {
        "title": "Best interests of the child",
        "text": """(2) The best interests of the child means the interests that appear, to the Director, or to a court, to be best for the child under the circumstances, having regard to all relevant considerations, including
(a) the safety of the child;
(b) the capacity of a parent to properly discharge parental obligations;
(c) the physical, mental and emotional needs of the child, and the appropriate care or treatment to meet those needs;
(d) the physical, mental and emotional level of development of the child;
(e) the views of the child, where appropriate;
(f) a secure place for the child and the development of a positive relationship as a member of a family;
(g) the love, affection and ties between the child and persons who have had custody of the child;
(h) the love, affection and ties between the child and other persons in the life of the child;
(i) the cultural, racial, linguistic and religious heritage of the child;
(j) if the child is aboriginal, the importance of preserving the cultural identity of the child;
(k) the capacity of persons other than a parent to exercise custody rights and duties respecting a child;
(l) the continuity of care for the child and the possible effect of disruption of that care on the child; and
(m) the difference in the concept of time, and the effect of delays in the resolution of proceedings on the child."""
    },
    "13": {
        "title": "Provision of child protection services / grounds for intervention",
        "text": """PROVISION OF CHILD PROTECTION SERVICES
13. (1) Where the Director concludes, after an investigation, that a child is in need of protection, the Director may offer child protection services to the parent.
(2) The Director may, following an investigation, enter into an agreement with a parent of a child who is in need of protection, where the parent voluntarily transfers temporary custody and guardianship of the child to the Director."""
    },
}

def fetch_pdf():
    if not os.path.exists(CACHE_FILE):
        urllib.request.urlretrieve(PDF_URL, CACHE_FILE)
    return CACHE_FILE

def get_text_file():
    if not os.path.exists(TEXT_CACHE):
        try:
            import pdfplumber
            full_text = ""
            with pdfplumber.open(CACHE_FILE) as pdf:
                for p in pdf.pages:
                    t = p.extract_text()
                    if t:
                        full_text += t + "\n"
            with open(TEXT_CACHE, "w") as f:
                f.write(full_text)
        except Exception as e:
            with open(TEXT_CACHE, "w") as f:
                f.write(f"Extraction error: {e}\nUsing cached verbatim sections only.")
    return TEXT_CACHE

def search_keyword(kw):
    results = []
    for k, v in VERBATIM.items():
        if kw.lower() in v["text"].lower():
            results.append((k, v["title"], v["text"]))
    return results

def main():
    parser = argparse.ArgumentParser(description="PEI CPA adapter")
    parser.add_argument("section", nargs="?", default=None)
    parser.add_argument("--search", default=None)
    args = parser.parse_args()
    fetch_pdf()
    get_text_file()
    if args.search:
        for sec, title, text in search_keyword(args.search):
            print(f"=== Section {sec}: {title} ===")
            print(text)
    elif args.section:
        key = args.section
        if key in VERBATIM:
            print(f"=== Section {key}: {VERBATIM[key]['title']} ===")
            print(VERBATIM[key]["text"])
        else:
            print(f"Section {key} not found in cached verbatim text.")
    else:
        print("Usage: python -m ca_law.scripts.youth_protection.pei_cpa <section> | --search <keyword>")

if __name__ == "__main__":
    main()