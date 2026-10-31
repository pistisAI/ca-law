#!/usr/bin/env python3
"""
Saskatchewan Child and Family Services Act (SS 1989-90, c C-7.2) Adapter
Fetches statute PDF from publications.saskatchewan.ca, caches locally, parses sections by number,
supports keyword search, and provides CLI access.

Source: https://publications.saskatchewan.ca/api/v1/products/460/formats/561/download
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import requests
    import pdfplumber
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False
    requests = None
    pdfplumber = None


@dataclass
class StatuteSection:
    """Represents a parsed statute section."""
    number: str
    heading: str
    text: str
    source_url: str


class SKCFSAdapter:
    """Adapter for the Saskatchewan Child and Family Services Act (C-7.2)."""

    PDF_URL = "https://publications.saskatchewan.ca/api/v1/products/460/formats/561/download"
    CACHE_DIR = Path(__file__).parent / ".cache"
    CACHE_PDF = CACHE_DIR / "sk_cfs_c7.2.pdf"
    CACHE_TEXT = CACHE_DIR / "sk_cfs_c7.2.txt"

    # Key sections we must verify (section number -> description)
    KEY_SECTIONS = {
        "11": "Child in need of protection (definition)",
        "4": "Best interests of the child (best interests test)",
        "17": "Apprehension (grounds for intervention)",
    }

    def __init__(self, force_refresh: bool = False):
        self.force_refresh = force_refresh
        self._full_text: Optional[str] = None
        self._sections: dict[str, StatuteSection] = {}
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def fetch(self) -> str:
        """Fetch the statute PDF from publications.saskatchewan.ca and extract text."""
        # Check if cached text exists and is fresh
        if self.CACHE_TEXT.exists() and not self.force_refresh:
            return self.CACHE_TEXT.read_text(encoding="utf-8")

        # Check if cached PDF exists
        if self.CACHE_PDF.exists() and not self.force_refresh:
            text = self._extract_text_from_pdf(self.CACHE_PDF)
            self.CACHE_TEXT.write_text(text, encoding="utf-8")
            return text

        if not HAS_DEPS:
            raise ImportError("requests and pdfplumber required for live fetch")
        # Download PDF
        response = requests.get(self.PDF_URL, timeout=60, verify=False)
        response.raise_for_status()

        # Cache PDF
        self.CACHE_PDF.write_bytes(response.content)

        # Extract and cache text
        text = self._extract_text_from_pdf(self.CACHE_PDF)
        self.CACHE_TEXT.write_text(text, encoding="utf-8")
        return text

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text from PDF using pdfplumber."""
        all_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
        return "\n\n".join(all_text)

    def parse(self) -> dict[str, StatuteSection]:
        """Parse sections from the cached text."""
        if self._sections:
            return self._sections

        text = self.fetch()
        self._full_text = text
        self._parse_sections(text)
        return self._sections

    def _parse_sections(self, text: str) -> None:
        """Parse sections from plain text using regex patterns."""
        # Pattern to match section headers like "11 A child is in need of protection if:"
        # or "4(1)" or "17(1)" followed by content
        # The Saskatchewan act uses formats like:
        # "11 A child is in need of protection if:"
        # "4(1) If a person or court is required..."
        # "17(1) If an officer or peace officer concludes..."

        section_starts = []

        # Pattern 1: Section with heading on same line (e.g., "11 A child is in need of protection if:")
        pattern1 = re.compile(r'^(\d{1,3})\s+([A-Z][^.]{10,100})$', re.MULTILINE)
        for m in pattern1.finditer(text):
            section_starts.append((m.start(), m.group(1), m.group(2).strip()))

        # Pattern 2: Subsection format (e.g., "4(1)", "11(1)", "17(1)")
        pattern2 = re.compile(r'^(\d{1,3})\((\d+)\)', re.MULTILINE)
        for m in pattern2.finditer(text):
            sec_num = m.group(1)
            sub_num = m.group(2)
            # Only treat as section start if it's subsection (1) - the main section content
            if sub_num == "1":
                # Look ahead for heading
                heading = self._extract_heading_near(text, m.start())
                section_starts.append((m.start(), sec_num, heading))

        # Sort by position and deduplicate (keep first occurrence of each section)
        section_starts.sort(key=lambda x: x[0])
        seen = set()
        unique_starts = []
        for pos, num, heading in section_starts:
            if num not in seen:
                seen.add(num)
                unique_starts.append((pos, num, heading))

        # Extract section text between starts
        for i, (start_pos, sec_num, heading) in enumerate(unique_starts):
            end_pos = unique_starts[i + 1][0] if i + 1 < len(unique_starts) else len(text)
            section_text = text[start_pos:end_pos].strip()

            # Clean up the text - remove page headers/footers
            section_text = self._clean_section_text(section_text)

            self._sections[sec_num] = StatuteSection(
                number=sec_num,
                heading=heading,
                text=section_text,
                source_url=self.PDF_URL,
            )

        # Ensure key sections are present even if parsing missed them
        self._ensure_key_sections(text)

    def _extract_heading_near(self, text: str, pos: int, window: int = 500) -> str:
        """Extract a heading near the given position."""
        snippet = text[pos:pos + window]
        lines = snippet.split("\n")
        for line in lines[1:6]:  # Skip the subsection line itself
            line = line.strip()
            if line and len(line) > 5 and not line[0].isdigit():
                # Likely a heading
                return line[:120]
        return ""

    def _clean_section_text(self, text: str) -> str:
        """Clean up section text by removing page headers/footers and artifacts."""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            # Skip page number lines (just numbers)
            if re.match(r'^\s*\d+\s*$', line):
                continue
            # Skip "CHILD AND FAMILY SERVICES c C-7.2" header lines
            if "CHILD AND FAMILY SERVICES" in line and "c C-7.2" in line:
                continue
            # Skip "--- PAGE X ---" markers
            if line.strip().startswith("--- PAGE"):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    def _ensure_key_sections(self, text: str) -> None:
        """Ensure key sections are parsed correctly by targeted extraction."""
        for sec_num in self.KEY_SECTIONS:
            # Always re-extract key sections to ensure we get the actual content, not TOC
            if sec_num == "11":
                self._extract_section_11(text)
            elif sec_num == "4":
                self._extract_section_4(text)
            elif sec_num == "17":
                self._extract_section_17(text)

    def _extract_section_11(self, text: str) -> None:
        """Extract section 11 - Child in need of protection."""
        # Find "11 A child is in need of protection if:"
        match = re.search(r'\b11\s+A child is in need of protection if:', text)
        if not match:
            return
        start = match.start()
        # Find next major section (12 or "Duty to report")
        end_match = re.search(r'\n\s*12\s+Duty to report\b', text[start:])
        end = start + end_match.start() if end_match else start + 5000
        section_text = text[start:end].strip()
        section_text = self._clean_section_text(section_text)
        self._sections["11"] = StatuteSection(
            number="11",
            heading="Child in need of protection",
            text=section_text,
            source_url=self.PDF_URL,
        )

    def _extract_section_4(self, text: str) -> None:
        """Extract section 4 - Best interests of the child."""
        # Find "Best interests of the child\n4(1)"
        match = re.search(r'Best interests of the child\n4\(1\)', text)
        if not match:
            # Alternative: find "4(1) If a person or court is required"
            match = re.search(r'\b4\(1\)\s+If a person or court is required', text)
        if not match:
            return
        start = match.start()
        # Find next major section (PART II or section 5)
        end_match = re.search(r'\n\s*(?:PART II|5\s+Family services)\b', text[start:])
        end = start + end_match.start() if end_match else start + 5000
        section_text = text[start:end].strip()
        section_text = self._clean_section_text(section_text)
        self._sections["4"] = StatuteSection(
            number="4",
            heading="Best interests of the child",
            text=section_text,
            source_url=self.PDF_URL,
        )

    def _extract_section_17(self, text: str) -> None:
        """Extract section 17 - Apprehension."""
        # Find the LAST occurrence of "Apprehension\n17(1)" to skip TOC
        matches = list(re.finditer(r'Apprehension\n17\(1\)', text))
        if not matches:
            matches = list(re.finditer(r'\b17\(1\)\s+If an officer or peace officer concludes', text))
        if not matches:
            return
        # Use the last match (actual section content, not TOC)
        match = matches[-1]
        start = match.start()
        # Find next section (18 or "Notification")
        end_match = re.search(r'\n\s*(?:18\s+Repealed|19\s+Notification)\b', text[start:])
        end = start + end_match.start() if end_match else start + 5000
        section_text = text[start:end].strip()
        section_text = self._clean_section_text(section_text)
        self._sections["17"] = StatuteSection(
            number="17",
            heading="Apprehension",
            text=section_text,
            source_url=self.PDF_URL,
        )

    def get_section(self, section_number: str) -> Optional[StatuteSection]:
        """Get a specific section by number."""
        sections = self.parse()
        return sections.get(section_number)

    def search(self, keyword: str, case_sensitive: bool = False) -> list[StatuteSection]:
        """Search sections by keyword."""
        sections = self.parse()
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(keyword), flags)
        results = []
        for section in sections.values():
            if pattern.search(section.text) or pattern.search(section.heading):
                results.append(section)
        return results

    def get_key_sections_verified(self) -> dict[str, bool]:
        """Verify that key sections are present and return status."""
        sections = self.parse()
        return {num: num in sections and len(sections[num].text) > 100 for num in self.KEY_SECTIONS}

    def get_source_urls(self) -> list[str]:
        """Return source URLs used."""
        return [self.PDF_URL]


def format_section(section: StatuteSection, verbose: bool = False) -> str:
    """Format a section for output."""
    if verbose:
        return f"Section {section.number}: {section.heading}\nSource: {section.source_url}\n\n{section.text}"
    return section.text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Saskatchewan Child and Family Services Act (C-7.2) - Section lookup and search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ca_law.scripts.youth_protection.sk_cfs 11
  python -m ca_law.scripts.youth_protection.sk_cfs 4
  python -m ca_law.scripts.youth_protection.sk_cfs 17
  python -m ca_law.scripts.youth_protection.sk_cfs --search "child in need of protection"
  python -m ca_law.scripts.youth_protection.sk_cfs --search "best interests" --verbose
  python -m ca_law.scripts.youth_protection.sk_cfs --verify
        """,
    )
    parser.add_argument("section", nargs="?", help="Section number to retrieve (e.g., 11, 4, 17)")
    parser.add_argument("--search", "-s", help="Search keyword across all sections")
    parser.add_argument("--verify", "-v", action="store_true", help="Verify key sections are present")
    parser.add_argument("--verbose", action="store_true", help="Verbose output with headings and source URLs")
    parser.add_argument("--refresh", action="store_true", help="Force refresh cache from source")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    adapter = SKCFSAdapter(force_refresh=args.refresh)

    if args.verify:
        verified = adapter.get_key_sections_verified()
        output = {
            "key_sections_verified": verified,
            "source_urls": adapter.get_source_urls(),
        }
        if args.json:
            print(json.dumps(output, indent=2))
        else:
            for num, present in verified.items():
                status = "\u2713" if present else "\u2717"
                print(f"  {status} Section {num}: {adapter.KEY_SECTIONS[num]}")
            print(f"\nSource: {adapter.get_source_urls()[0]}")
        return 0 if all(verified.values()) else 1

    if args.search:
        results = adapter.search(args.search)
        if args.json:
            print(json.dumps([
                {"number": s.number, "heading": s.heading, "text": s.text, "source_url": s.source_url}
                for s in results
            ], indent=2))
        else:
            if not results:
                print(f"No sections found matching '{args.search}'")
            for section in results:
                print(format_section(section, args.verbose))
                print("---")
        return 0

    if args.section:
        section = adapter.get_section(args.section)
        if not section:
            print(f"Section {args.section} not found", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({
                "number": section.number,
                "heading": section.heading,
                "text": section.text,
                "source_url": section.source_url,
            }, indent=2))
        else:
            print(format_section(section, args.verbose))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())