#!/usr/bin/env python3
"""Yukon territorial statute section lookup from the official laws.yukon.ca site.

Use when the site must be reached through the local Camofox anti-detection
browser because direct curl/urllib gets a Cloudflare 403 (challenge).  The
official consolidated text of Yukon acts is served as bilingual (EN/FR) PDFs
under /cms/images/LEGISLATION/acts/<slug>.pdf, e.g.

    Motor Vehicles Act, R.S.Y. 2002, c. 153  ->  move.pdf
    Children's Law Act, R.S.Y. 2002, c. 31    ->  childrens.pdf
    (the PDF is titled "CHILDREN'S ACT").

Workflow:
  1. Resolve the statute to its consolidated PDF URL (built-in mapping, with
     an option to pass the slug/URL directly).
  2. Reach the site through Camofox (REST at $CAMOFOX_URL / localhost:9377):
       - open/adopt a tab, navigate to the PDF, POST /tabs/{id}/fetch-current-resource
     which saves the PDF as a server-side download artifact the plugin writes
     to $TMPDIR (= scratch) as  camofox-download-<uuid>-<file>.pdf.
  3. Copy the newest matching artifact, pdftotext the ENGLISH column by cropping
     the page to the left half (letter page: x=0, w=306), which drops the French
     column from the bilingual layout.
  4. Find the requested section marker and print the VERBATIM English body
     (heading kept; running page headers/footers, page numbers and the French
     gloss in « » stripped term-by-term) plus citation, source URL, retrieval date.

Never paraphrases a statute.

Usage:
    yt_law.py "Motor Vehicles Act" 1(2)
    yt_law.py "Motor Vehicles Act" 2
    yt_law.py --slug move 1(2)

Exit codes: 0 found; 1 not found/usage; 2 network/source/transport error.
"""
from __future__ import annotations

import argparse, glob, os, re, shutil, subprocess, sys, tempfile
import urllib.request
from datetime import date
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) ca-law-skill/yt/1.0"
SITE = "https://laws.yukon.ca"
PDF_DIR = SITE + "/cms/images/LEGISLATION/acts"
# statute name (lower)  ->  slug.pdf filename
MAPPING = {
    "motor vehicles act": "move.pdf",
    "movement act": "move.pdf",
    "children's law act": "childrens.pdf",
    "children's act": "childrens.pdf",
    "children act": "childrens.pdf",
}
# citation label, chapter (text used in the printed citation line)
CITATION = {
    "move.pdf": ("Motor Vehicles Act", "R.S.Y. 2002, c. 153"),
    "childrens.pdf": ("Children's Law Act", "R.S.Y. 2002, c. 31"),
}


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def camofox_url() -> str:
    return os.environ.get("CAMOFOX_URL") or "http://127.0.0.1:9377"


def resolve_pdf(statute: str) -> tuple[str, str]:
    """statute -> (pdf_url, slug)."""
    key = statute.strip().lower()
    if key in MAPPING:
        slug = MAPPING[key]
        return f"{PDF_DIR}/{slug}", slug
    if key.startswith("http"):
        # passed a full URL to a PDF
        base = key.split("/")[-1]
        return key, base
    # allow "--slug move" style: key is just a filename fragment
    if re.match(r"^[\w\-]\.pdf$", key) or re.match(r"^[\w\-]+$", key) and not (" " in key):
        fn = key if key.endswith(".pdf") else key + ".pdf"
        return f"{PDF_DIR}/{fn}", fn
    raise KeyError(f"yt_law: unknown statute '{statute}' (known: {', '.join(sorted(set(MAPPING)))})")


# ---- camofox transport ----------------------------------------------------
def pf(res, code):
    """Print camofox error to stderr and exit(2)."""
    try:
        msg = res.json().get("error") or res.text[:300]
    except Exception:
        msg = res.text[:300]
    print(f"yt_law: camofox error ({code}): {msg}", file=sys.stderr)
    sys.exit(2)


def camofox_fetch(script_dir: Path, userId: str, pdf_url: str, filename: str) -> Path:
    """Reach the PDF through Camofox and return a local path to the bytes."""
    import requests
    base = camofox_url()
    tab = None
    try:
        # open a tab (reuse if we land on blank first tab)
        r = requests.post(base + "/tabs", json={"userId": userId, "url": pdf_url}, timeout=90)
        if r.status_code == 200:
            tab = r.json().get("tabId")
        else:
            # fall back to POST /tabs/open
            r2 = requests.post(base + "/tabs/open", json={"userId": userId, "url": pdf_url}, timeout=90)
            if r2.status_code == 200 and r2.json().get("tabId"):
                tab = r2.json()["tabId"]
            else:
                pf(r2, r2.status_code)
        if not tab:
            sys.exit(2)
        # ensure it resolved to the PDF (report HTTP status anyway)
        nav = requests.post(base + f"/tabs/{tab}/navigate",
                            json={"userId": userId, "url": pdf_url}, timeout=90)
        if nav.status_code != 200:
            pf(nav, nav.status_code)
        # save the current resource as a download artifact
        dl = requests.post(base + f"/tabs/{tab}/fetch-current-resource",
                           json={"userId": userId}, timeout=90)
        if dl.status_code not in (200, 415):
            pf(dl, dl.status_code)
        # locate the artifact the plugin surfaces under $TMPDIR/scratch
        tmp = os.environ.get("TMPDIR") or tempfile.gettempdir()
        found = None
        for pat in (
            f"{tmp}/camofox-download-*{filename}",
            f"{tmp}/**/camofox-download-*{filename}",
        ):
            cand = sorted(glob.glob(pat, recursive=True), key=os.path.getmtime, reverse=True)
            if cand:
                found = cand[0]
                break
        if not found:
            # try across scratch dir (plugin may write under a subdir)
            scratch = hermes_home() / "cache" / "scratch"
            cand = sorted(scratch.glob(f"camofox-download-*{filename}"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            found = str(cand[0]) if cand else None
        if not found:
            print("yt_law: PDF download artifact not found under camofox scratch dir.",
                  file=sys.stderr)
            sys.exit(2)
        dest = script_dir / filename
        shutil.copyfile(found, dest)
        return dest
    except ImportError:
        print("yt_law: 'requests' not installed (pip install requests).", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"yt_law: camofox transport failed: {e}", file=sys.stderr)
        sys.exit(2)


def fetch_pdf(pdf_url: str, slug: str, script_dir: Path) -> Path:
    dest = script_dir / slug
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    userId = os.environ.get("CAMOFOX_USER_ID") or f"ca-law-yt-{os.environ.get('USER','user')}"
    try:
        return camofox_fetch(script_dir, userId, pdf_url, slug)
    except SystemExit:  # camofox path failed; try plain http as last resort
        pass
    # last resort: plain fetch (likely 403 on this site, but harmless to try)
    try:
        req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=90) as r:
            blob = r.read()
        if blob.startswith(b"%PDF"):
            dest.write_bytes(blob)
            return dest
    except Exception as e:
        raise SystemExit(f"yt_law: could not obtain PDF via camofox or http ({e}). Exiting.")
    raise SystemExit("yt_law: could not obtain the PDF.")


# ---- text extraction -------------------------------------------------------
def en_column(pdf: Path) -> str:
    """pdftotext the English (left) column of the bilingual letter page."""
    try:
        tmp = Path(tempfile.mkstemp(suffix=".txt")[1])
        subprocess.run(["pdftotext", "-raw", "-x", "0", "-y", "0",
                        "-W", "302", "-H", "792",
                        str(pdf), str(tmp)], check=True, capture_output=True)
        text = tmp.read_text(encoding="utf-8", errors="replace")
        tmp.unlink()
        return text
    except (FileNotFoundError, subprocess.CalledProcessError):
        # retry without crop box (whole page; French interleaves but still usable)
        tmp = Path(tempfile.mkstemp(suffix=".txt")[1])
        subprocess.run(["pdftotext", "-raw", str(pdf), str(tmp)],
                       check=True, capture_output=True)
        text = tmp.read_text(encoding="utf-8", errors="replace")
        tmp.unlink()
        return text


# running page headers / footers / page numbers / French gloss trails
HDR = re.compile(
    r"^(?:CHAPTER\s+\d+|.*?ACT\s*|"
    r"REVISED STATUTES OF THE YUKON\s+\d{4}\s*\d*|REVISED STATUTES OF THE YUKON\s*\d*|"
    r"STATUTES OF THE YUKON\s+|"
    r"(?:\(?(?:SOU|S\.Y\.|R\.S\.)[\s\w\.,/:;\-()]+?\s+\d{1,3}\s*)$)|"
    r"^\d{1,3}\s*$")
FR_GLOSS = re.compile(r"\s*«[^»]*»\s*$")        # trailing French term gloss
FR_INLINE = re.compile(r"\s*«[^»]*»")            # inline French gloss (rare)
SECT = re.compile(r"^(?:\((\d{1,3})\)\s+|\s{0,3})?(\d{1,3})(?:\((\d{1,3})\))?\s+(.+)$")
SUBSECT = re.compile(r"^\((\d{1,3})\)\s+(.+)$")  # continuation subsection, e.g. "(2) ..."
RSCITE = re.compile(r"(?:R\.S\.|S\.Y\.|S\.O\.|RSV)", re.I)


def clean_line(line: str) -> str:
    s = line.strip()
    if not s:
        return ""
    if HDR.match(s):
        return ""
    s = FR_GLOSS.sub("", s)
    return s


def extract_section(text: str, target_section: str) -> tuple[str, str] | None:
    """Return (heading, verbatim_body) for target_section, or None.

    Handles 'N' (whole section) and 'N(M)' (a subsection)."""
    sect_match = re.match(r"^(\d{1,3})(?:\((\d{1,3})\))?$", target_section.strip())
    if not sect_match:
        return None
    want_n, want_m = sect_match.group(1), sect_match.group(2)

    lines = [clean_line(l) for l in text.splitlines()]
    # collapse blanks but remember original structure
    # find all lines that START a top-level section marker: ^<N>(<N>)  or  ^<N> <cap>
    starts = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(\d{1,3})(?:\((\d{1,3})\))?\s+[A-Za-z(“\u201c]", ln)
        if m:
            starts.append((i, m.group(1), m.group(2)))
    # locate the top-level section block containing want_n
    cand = [s for s in starts if s[1] == want_n]
    if not cand:
        return None
    # a section may begin with an unnumbered heading line (e.g. "Registrar and staff")
    # we recover the heading = nearest preceding non-blank line(s) before the marker
    # that are not themselves "PART"/"DIVISION" and not another section marker.
    idx = cand[0][0]
    heading_parts = []
    j = idx - 1
    while j >= 0:
        if not lines[j]:
            break
        if re.match(r"^PART\b", lines[j]):
            break
        if RSCITE.search(lines[j]):
            break
        if re.match(r"^\(", lines[j]):  # subsection continuation -> belongs to prior section
            break
        if re.match(r"^(\d{1,3})(?:\((\d{1,3})\))?\s", lines[j]):
            break
        heading_parts.insert(0, lines[j])
        j -= 1
    NR = re.compile(r"REVISED STATUTES OF THE YUKON|CHAPTER\s+\d+|STATUTES OF THE YUKON")
    heading = " — ".join(h.strip() for h in heading_parts if h.strip() and not NR.search(h))

    if want_m is None:
        # whole section: from marker to next top-level section (>= want_n but different)
        body = [lines[idx]]
        k = idx + 1
        while k < len(lines):
            if not lines[k]:
                k += 1
                continue
            m2 = re.match(r"^(\d{1,3})(?:\((\d{1,3})\))?\s+[A-Za-z(“\u201c]", lines[k])
            if m2 and m2.group(1) != want_n:
                break
            m3 = SUBSECT.match(lines[k])
            if m3:
                body.append(lines[k])
                k += 1
                continue
            if re.match(r"^\(?\([a-zA-Z]\)\s*$", lines[k]):  # bare marker line
                k += 1
                continue
            body.append(lines[k])
            k += 1
        body_text = "\n".join(b for b in body if b)
        return (heading, trim_after_cite(body_text))

    # subsection N(M): start at its marker line and stop at next subsection or next section
    body = []
    k = idx + 1
    capturing = False
    # subsection "1" (or a bare section) begins at the top-level marker line itself
    if want_m == "1":
        body.append(lines[idx])
        capturing = True
        k = idx + 1
    while k < len(lines):
        ln = lines[k]
        if not ln:
            if capturing:
                break
            k += 1
            continue
        m2 = re.match(r"^(\d{1,3})(?:\((\d{1,3})\))?\s+[A-Za-z(“\u201c]", ln)
        if m2 and m2.group(1) != want_n:
            break
        sm = SUBSECT.match(ln)
        if sm:
            if sm.group(1) == want_m:
                body.append(ln)
                capturing = True
                k += 1
                continue
            if capturing:
                break
            k += 1
            continue
        if capturing:
            body.append(ln)
        k += 1
    if not body:
        return (heading, "")
    return (heading, trim_after_cite("\n".join(body)))


def trim_after_cite(body_text: str) -> str:
    """Drop trailing heading lines that follow the section's history footer (R.S. / S.Y.)."""
    body_lines = body_text.splitlines()
    # last line that is a history citation (R.S., S.Y., etc.)
    last_cite = -1
    for i, ln in enumerate(body_lines):
        if RSCITE.search(ln):
            last_cite = i
    if last_cite >= 0 and last_cite < len(body_lines) - 1:
        body_lines = body_lines[: last_cite + 1]
    return "\n".join(body_lines)


# ---- main ------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("statute", nargs="?", help="statute name, slug, or PDF URL")
    ap.add_argument("section", nargs="?", help="section, e.g. 1, 1(2)")
    ap.add_argument("--slug", help="pass the PDF slug/filename directly")
    ap.add_argument("--search", help="(unused) retained for CLI symmetry")
    args = ap.parse_args()

    if args.slug:
        statute_or_url = args.slug
        section = args.section
    elif args.statute and args.section:
        statute_or_url = args.statute
        section = args.section
    else:
        ap.print_help()
        return 1

    try:
        pdf_url, slug = resolve_pdf(statute_or_url)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1

    script_dir = Path(__file__).resolve().parent
    try:
        pdf = fetch_pdf(pdf_url, slug, script_dir)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    raw = en_column(pdf)
    res = extract_section(raw, section)
    if not res:
        print(f"yt_law: section '{section}' not found in {slug}.", file=sys.stderr)
        return 1
    heading, body = res
    if not body:
        print(f"yt_law: section '{section}' not found in {slug}.", file=sys.stderr)
        return 1

    name, cite = CITATION.get(slug, (slug.replace(".pdf", ""), f"R.S.Y. 2002, c. {slug[:4]}"))
    print(name)
    if heading:
        print(heading)
    print(f"Citation: {cite}, s. {section}")
    print(f"Source:   {SITE} (official consolidated text, {slug})")
    print(f"PDF:      {pdf_url}")
    print(f"Retrieved: {date.today().isoformat()}")
    print("-" * 60)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
