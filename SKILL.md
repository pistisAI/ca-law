---
name: ca-law
description: "Read Canadian and Quebec statutes verbatim with citation."
version: 1.0.0
author: "Zoid Maltek (zoid), Christopher Maltais, Hermes Agent"
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [law, canada, quebec, statutes, legal, court, citation]
    related_skills: []
---

# Canadian & Québécois Statute Lookup (`ca-law`)

Read the **exact text of Canadian federal and Quebec provincial statutes** straight from the official publishers — Justice Canada (federal, XML per act) and Légis Québec (provincial, HTML) — with proper citation, edition date, and source attribution. Built for Christopher's court cases (M-314-C under the Criminal Code, family/DPJ matters under the youth-protection and civil code provisions).

It does **not** give legal advice, summarize cases, or replace a lawyer. It returns the verbatim statute text with citation, so a question like "what does art. 266 C.cr. say" or "what is the wording of art. 1457 C.c.Q." gets an exact, sourced answer you can actually rely on.

## When to Use

- "What does section/article X of [Canadian/Quebec] law say?"
- Reading the **Criminal Code (C.cr.)**, **Code civil du Québec (C.c.Q.)**, **Code de procédure civile**, **Loi sur la protection de la jeunesse** (family/DPJ context), **Charte des droits**, federal acts by chapter (e.g. `C-46`, `F-11`), or a specific article/section verbatim.
- Court prep where you need the *current* official text of a cited provision.
- **Don't use for:** case law (CanLII is better for decisions — not covered here), interpreting or advising on the law, or non-federal/non-Quebec provincial law (Alberta, Ontario, etc. are out of scope).

## Prerequisites

- `curl` on PATH, and network access to `laws.justice.gc.ca`, `laws-lois.justice.gc.ca`, `www.legisquebec.gouv.qc.ca`.
- A **browser User-Agent is required** for both sites (they WAF/403 a botless curl — be HTTP 200, not 403).
- Scripts stay **HTTP 200** locally; a section that isn't found or a source that's down returns a clear error — never a guessed quote.

## How to Run

The skill ships a federal script, a Quebec script, and per-province adapters in `scripts/`:

```bash
# Federal law: read a section by chapter + section number
python3 scripts/ca_law.py C-46 266          # Criminal Code, s. 266
python3 scripts/ca_law.py C-46 --search "assault"   # search within the act

# Quebec law: read an article by law slug + article number
python3 scripts/qc_law.py CCQ-1991 1457     # Code civil du Québec, art. 1457
python3 scripts/qc_law.py LPJ 38            # Loi sur la protection de la jeunesse, art. 38

# Alberta law: read a section by RSA chapter id + section number
python3 scripts/provinces/ab_law.py T-6 1   # Traffic Safety Act, s.1

# Ontario: e-Laws JSON API
python3 scripts/provinces/on_law.py 90c43 30    # Courts of Justice Act, s.30

# British Columbia: BCLaws civix HTML
python3 scripts/provinces/bc_law.py 96338_01 2  # Offence Act, s.2

# Manitoba: CCSM HTML
python3 scripts/provinces/mb_law.py H60 1       # Highway Traffic Act, s.1

# Newfoundland & Labrador: House of Assembly HTML
python3 scripts/provinces/nl_law.py L-18 1      # Liquor Control Act, s.1

# Prince Edward Island: LCO PDF
python3 scripts/provinces/pe_law.py H-5 1       # Highway Traffic Act, s.1
```

The canonical invocation is via the `terminal` tool (frames it as `terminal(command="python3 scripts/ca_law.py ...")`). Scripts cache fetched documents under `<HERMES_HOME>/plugin-data/ca-law/cache/` so repeat lookups hit disk, not the network.

## Coverage map (jurisdiction → script → source)

- **Federal (C.cr., R.S.C. acts, chapter e.g. C-46):** `ca_law.py` — Justice Canada consolidated XML (`laws.justice.gc.ca/eng/XML/<Chapter>.xml`).
- **Quebec (C.c.Q., LPJ/P-34.1, Légis Québec slug e.g. CCQ-1991):** `qc_law.py` — Légis Québec HTML.
- **Ontario:** `provinces/on_law.py` — e-Laws JSON API (React app; use the JSON endpoint, not the page HTML).
- **British Columbia:** `provinces/bc_law.py` — BCLaws civix consolidated HTML (id ends `_01` for the main consolidation, e.g. Offence Act = `96338_01`).
- **Alberta:** `provinces/ab_law.py` — King's Printer consolidation PDF (`kings-printer.alberta.ca/documents/Acts/...`) via pdftotext.
- **Manitoba:** `provinces/mb_law.py` — CCSM consolidated HTML (`web2.gov.mb.ca/laws/statutes/ccsm/<chap>.php`, id lowercased + zero-padded to 3).
- **Newfoundland & Labrador:** `provinces/nl_law.py` — House of Assembly statute HTML (`.htm`, not `.html`; cp1252).
- **Prince Edward Island:** `provinces/pe_law.py` — Legislative Counsel Office consolidation PDF via pdftotext.
- **Saskatchewan:** `provinces/sk_law.py` — Office of the King's Printer Freelaw API → official consolidated PDF via pdftotext (single-host TLS verify disabled; API id per statute).
- **Nova Scotia:** `provinces/ns_law.py` — nslegislature.ca consolidation PDF via pdftotext (HTML fallback). Some acts consolidated under renamed titles (e.g. Maintenance and Custody → Parenting and Support).
- **New Brunswick:** `provinces/nb_law.py` — laws.gnb.ca consolidated HTML (English column; chapter id like `M-17`).
- **Yukon:** `provinces/yt_law.py` — laws.yukon.ca consolidated PDF (Cloudflare bot-walled → Camofox browser REST at `$CAMOFOX_URL` to download; pdftotext English-column).
- **Northwest Territories:** `provinces/nt_law.py` — gnwt.ca Legacy Justice consolidated PDF (justice.gov.nt.ca 504s; mirror serves identical official file), pdftotext bilingual-column split.
- **Full coverage reached 2026-10-31: federal + all 10 provinces + Yukon, NWT, Nunavut-to-add (NU not yet built). Case law (CanLII) is out of scope.

## Procedure

1. **Identify jurisdiction** from the citation: `C.cr.` / `R.S.C.` / a federal chapter like `C-46` / `F-11` → federal; `C.c.Q.` / `C.p.c.` / a Légis Québec slug (`CCQ-1991`, `LPJ`, `CQLR c ...`) → Quebec; the rest → the matching province script per the coverage map above.
2. **Federal:** map the chapter to its URL slug and fetch the XML, parse the section by number, return its text + the act's "current to" edition date + amendment date.
3. **Quebec:** fetch the Légis Québec page for the law, parse the article by number, return the verbatim text + consolidation date.
4. **Return** the text verbatim, with a citation line like `s. 266 C.cr. (R.S.C., 1985, c. C-46)` or `art. 1457 C.c.Q.`, the official source, the retrieved date, and edition data. If unavailable, report the exact error — never fabricate a provision.
5. **Verify** by re-reading the returned text against the source before quoting it to Christopher (rule: quote only verbatim, with source).

## Pitfalls

- **WAF/403:** if curl is HTTP 403 or CloudFront-blocked, add the browser UA (`-A "Mozilla/5.0 ..."`). The scripts set it by default.
- **Justice XML slug differs from chapter:** `C-46` → URL `C-46` in `laws.justice.gc.ca/eng/XML/`; verify the fetched XML's home title before trusting it.
- **Quebec slug not stable:** a law's Légis Québec slug (e.g. `CCQ-1991` for the civil code) must match the site's current slug; if a look-up 404s, search the site for the law's title to find the current slug. The scripts print the fetched title so a mismatch is visible.
- **Never paraphrase in place of verbatim text** — these are statutes, wording is legally binding. If only a partial match is safest, return the exact substring and say that's what it is.
- **Provincial ≠ federal:** `ca_law.py` and `qc_law.py` cover federal and Quebec only; every other province has its own adapter in `scripts/provinces/` (see coverage map). Match the citation to the right script — don't assume one script handles a province it isn't wired for.

## Verification

- `python3 scripts/ca_law.py C-46 266` returns text that begins with the real Criminal Code s. 266 (offence of assault), a source line pointing to `laws.justice.gc.ca`, and a "current to" date — no "Could not connect", no 403, no empty.
- `python3 scripts/qc_law.py CCQ-1991 1457` returns the Code civil art. 1457 (conditions of civil liability) verbatim with a `legisquebec.gouv.qc.ca` source line.
- Re-run after a cold cache clears: the second run must return the same text from disk (check the cache-state line says `cached`, not `fresh`).
---
