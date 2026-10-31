"""
Youth Protection / Child Services statutes across Canada.

Each province/territory has its own child protection legislation.
This module provides verbatim lookup via the same pattern as ca_law.py / qc_law.py.

QC: Loi sur la protection de la jeunesse (LPJ, P-34.1) → via qc_law.py
ON: Child, Youth and Family Services Act, 2017 (SO 2017, c 14, Sched 1)
BC: Child, Family and Community Service Act (RSBC 1996, c 46)
AB: Child, Youth and Family Enhancement Act (RSA 2000, c C-12)
SK: The Child and Family Services Act (SS 1989-90, c C-7.2)
MB: The Child and Family Services Act (CCSM c C80)
NS: Children and Family Services Act (SNS 1990, c 5)
NB: Family Services Act (RSNB 1980, c F-2.2)
NL: Children, Youth and Families Act (SNL 2021, c 10)
PEI: Child Protection Act (RSPEI 1988, c C-5.1)
YT: Child and Family Services Act (SY 2008, c 1)
NT: Child and Family Services Act (SNWT 1997, c 13)
NU: Child and Family Services Act (SNu 2021, c 7)
"""
# QC LPJ (working - wraps qc_law.py)
from .qc_lpj import get_article as qc_get_article, search as qc_search, KEY_ARTICLES as qc_key_articles

# Other provinces (stubs - implement proper parsers as needed)
# from .on_cyfsa import search as on_search, get_section as on_get_section
# from .bc_cfcsa import search as bc_search, get_section as bc_get_section
# from .ab_cyfea import search as ab_search, get_section as ab_get_section
# from .sk_cfs import search as sk_search, get_section as sk_get_section
# from .mb_cfs import search as mb_search, get_section as mb_get_section
# from .ns_cfs import search as ns_search, get_section as ns_get_section
# from .nb_fsa import search as nb_search, get_section as nb_get_section
# from .nl_cyfa import search as nl_search, get_section as nl_get_section
# from .pei_cpa import search as pei_search, get_section as pei_get_section
# from .yt_cfs import search as yt_search, get_section as yt_get_section
# from .nt_cfs import search as nt_search, get_section as nt_get_section
# from .nu_cfs import search as nu_search, get_section as nu_get_section

__all__ = [
    "qc_get_article", "qc_search", "qc_key_articles",
]
