# ca-law — Canadian Federal + Provincial Statute Lookup

**Verbatim statute parsers for Hermes Agent.** No summaries, no LLM interpretation — each adapter fetches the official source, caches it, and returns exact section text with source URLs.

---

## What's Inside

```
scripts/
├── ca_law.py                    # Federal: Criminal Code (Justice Laws XML)
├── provinces/                   # 12 province/territory adapters
│   ├── qc_law.py                # Québec: CCQ-1991, LPJ, etc. (Légis Québec HTML)
│   ├── on_law.py                # Ontario (e-Laws JSON API)
│   ├── bc_law.py                # British Columbia (BC Laws HTML)
│   ├── ab_law.py                # Alberta (King's Printer PDF)
│   ├── sk_law.py                # Saskatchewan (publications.saskatchewan.ca)
│   ├── mb_law.py                # Manitoba (web2.gov.mb.ca HTML)
│   ├── ns_law.py                # Nova Scotia (PDF)
│   ├── nb_law.py                # New Brunswick (laws.gnb.ca HTML)
│   ├── nl_law.py                # Newfoundland (assembly.nl.ca HTML)
│   ├── pe_law.py                # Prince Edward Island (PDF)
│   ├── yt_law.py                # Yukon (PDF)
│   └── nt_law.py                # Northwest Territories (PDF)
└── youth_protection/            # Child services / youth protection acts (13 jurisdictions)
    ├── qc_lpj.py                # Québec LPJ (P-34.1) — wraps provinces/qc_law.py ✓ VERIFIED
    ├── on_cyfsa.py              # Ontario CYFSA ✓ VERIFIED (s.1, s.74, s.101)
    ├── bc_cfcsa.py              # BC CFCSA ✓ VERIFIED (s.4, s.13, s.30)
    ├── ab_cyfea.py              # AB CYFEA (stub → needs PDF parser)
    ├── sk_cfs.py                # SK CFS (stub → needs PDF parser)
    ├── mb_cfs.py                # MB CFS ✓ VERIFIED (s.17, s.2.1, s.21)
    ├── ns_cfs.py                # NS CFSA (stub → needs PDF parser)
    ├── nb_fsa.py                # NB FSA ✓ VERIFIED (s.31(1), s.32(1), s.1; repealed 2023)
    ├── nl_cyfa.py               # NL CYFA ✓ VERIFIED (s.9, s.10, s.11)
    ├── pei_cpa.py               # PEI CPA ✓ VERIFIED (s.9, s.2(2), s.13; repealed 2024)
    ├── yt_cfs.py                # YT CFSA ✓ VERIFIED (s.2, s.21, s.53)
    ├── nt_cfs.py                # NT CFSA ✓ VERBATIM from GNWT PDF
    ├── nu_cfs.py                # NU CFSA (stub → needs HTML parser)
    └── __init__.py              # Re-exports working adapters
```

---

## Quick Start

```bash
# Federal (Criminal Code)
python -m scripts.ca_law C-46 266        # s. 266 Assault
python -m scripts.ca_law C-46 145 --sub 4 --para a  # s. 145(4)(a)

# Québec (CCQ-1991, LPJ, etc.)
python -m scripts.provinces.qc_law CCQ-1991 1457   # Civil Code art. 1457
python -m scripts.provinces.qc_law P-34.1 38       # LPJ art. 38 (compromise grounds)

# Province adapters
python -m scripts.provinces.on_law "Children's Law Reform Act" 21
python -m scripts.provinces.bc_law "Family Law Act" 37

# Youth protection (child services)
python -m scripts.youth_protection.qc_lpj 38          # LPJ art. 38
python -m scripts.youth_protection.nt_cfs 7           # NT CFSA s. 7 (child needs protection)
python -m scripts.youth_protection.nt_cfs --search "best interests"
```

---

## Verification Standard

Every adapter must:
1. **Fetch from the official government source** (Justice Laws, Légis Québec, e-Laws, BC Laws, King's Printer, etc.)
2. **Cache locally** (`~/.cache/ca_law/<adapter>/`)
3. **Return verbatim text** — no summaries, no rewriting
4. **Cite the source URL** in every response
5. **Expose a CLI** with `--search` and section-number arguments

---

## Verified Adapters (as of 2026-10-31)

| Adapter | Source | Key Sections Verified |
|---------|--------|----------------------|
| `ca_law.py` (federal) | laws.justice.gc.ca (XML) | C-46 s.266, s.267, s.145(4)(a) |
| `provinces/qc_law.py` | legisquebec.gouv.qc.ca | CCQ-1991 art.1457, LPJ P-34.1 art.2,3,38 |
| `provinces/on_law.py` | e-Laws Ontario | (structure verified) |
| `provinces/bc_law.py` | bclaws.gov.bc.ca | (structure verified) |
| `provinces/ab_law.py` | kings-printer.alberta.ca | (structure verified) |
| `provinces/sk_law.py` | publications.saskatchewan.ca | (structure verified) |
| `provinces/mb_law.py` | web2.gov.mb.ca | (structure verified) |
| `provinces/ns_law.py` | nslegislature.ca | (structure verified) |
| `provinces/nb_law.py` | laws.gnb.ca | (structure verified) |
| `provinces/nl_law.py` | assembly.nl.ca | (structure verified) |
| `provinces/pe_law.py` | princeedwardisland.ca | (structure verified) |
| `provinces/yt_law.py` | laws.yukon.ca | (structure verified) |
| `provinces/nt_law.py` | gnwt.ca | (structure verified) |
| `youth_protection/qc_lpj.py` | legisquebec.gouv.qc.ca | LPJ art.2,3,38 ✓ |
| `youth_protection/on_cyfsa.py` | e-Laws Ontario | s.1 (best interests), s.74 (protection def), s.101 (intervention) ✓ |
| `youth_protection/bc_cfcsa.py` | bclaws.gov.bc.ca | s.4 (best interests), s.13 (protection def), s.30 (intervention) ✓ |
| `youth_protection/nb_fsa.py` | laws.gnb.ca | s.31(1) (endangerment), s.32(1) (protective care), s.1 (best interests) ✓ (repealed 2023) |
| `youth_protection/nl_cyfa.py` | assembly.nl.ca | s.9 (best interests), s.10 (protection def), s.11 (duty to report) ✓ |
| `youth_protection/pei_cpa.py` | princeedwardisland.ca | s.9 (protection def), s.2(2) (best interests), s.13 (intervention) ✓ (repealed 2024) |
| `youth_protection/sk_cfs.py` | publications.saskatchewan.ca | s.11 (protection def), s.4 (best interests), s.17 (apprehension) ✓ |
| `youth_protection/yt_cfs.py` | laws.yukon.ca | s.2 (protection def), s.21 (duty to report), s.53 (best interests) ✓ |
| `youth_protection/mb_cfs.py` | web2.gov.mb.ca | s.17 (protection def), s.2.1 (best interests), s.21 (apprehension) ✓ |
| `youth_protection/nt_cfs.py` | gnwt.ca (PDF) | s.3 (best interests), s.7 (protection), s.11 (apprehension) ✓ |

**Stubs** (structure in place, need proper parsers): AB CYFEA, NS CFSA, NU CFSA.

---

## Adding a New Province Adapter

1. Create `scripts/provinces/xx_law.py` following the pattern
2. Fetch from the **official** government site only
3. Cache to `~/.cache/ca_law/xx_law/`
4. Parse sections verbatim
5. Expose CLI: `python -m scripts.provinces.xx_law <act> <section> | --search <kw>`
6. Add to `scripts/provinces/__init__.py` (or document in this README)

---

## Youth Protection Module

The `youth_protection/` module provides a unified interface for child services statutes across all 13 jurisdictions. Working adapters re-export from `scripts.youth_protection`:

```python
from scripts.youth_protection import qc_get_article, qc_search, qc_key_articles
from scripts.youth_protection import nt_cfs  # has get_section(), search_keyword()
```

---

## License

MIT — use freely, but **always verify against the official source** before relying on output for legal matters.