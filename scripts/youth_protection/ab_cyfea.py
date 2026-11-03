#!/usr/bin/env python3
"""
Alberta Child, Youth and Family Enhancement Act (RSA 2000, c C-12) Adapter
Fetches PDF from King's Printer, caches locally, extracts and parses sections.
"""

import os
import sys
import re
import json
import argparse
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False


class ABCYFEAAdapter:
    """Adapter for Alberta Child, Youth and Family Enhancement Act."""
    
    SOURCE_URL = "https://kings-printer.alberta.ca/documents/Acts/C12.pdf"
    CACHE_DIR = Path.home() / ".cache" / "ab_cyfea"
    PDF_PATH = CACHE_DIR / "C12.pdf"
    TEXT_CACHE_PATH = CACHE_DIR / "full_text.json"
    
    # Key section patterns for parsing
    SECTION_PATTERN = re.compile(r'^\s*(\d+(?:\.\d+)?)(?:\((\d+)\))?\s')
    
    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._full_text: Optional[str] = None
        self._sections: Dict[str, str] = {}
        self._parsed = False
    
    def fetch_pdf(self, force: bool = False) -> Path:
        """Download PDF from King's Printer if not cached or forced."""
        if self.PDF_PATH.exists() and not force:
            return self.PDF_PATH
        
        print(f"Fetching PDF from {self.SOURCE_URL}...")
        req = Request(self.SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urlopen(req, timeout=60) as response:
                content = response.read()
                # Verify it's a PDF
                if not content.startswith(b'%PDF'):
                    raise ValueError("Downloaded content is not a valid PDF")
                self.PDF_PATH.write_bytes(content)
                print(f"Cached PDF to {self.PDF_PATH} ({len(content)} bytes)")
        except (URLError, HTTPError) as e:
            if self.PDF_PATH.exists():
                print(f"Download failed, using cached version: {e}")
                return self.PDF_PATH
            raise RuntimeError(f"Failed to fetch PDF: {e}")
        return self.PDF_PATH
    
    def extract_text(self) -> str:
        """Extract full text from PDF using pdfplumber or PyPDF2."""
        if self._full_text is not None:
            return self._full_text
        
        # Try cached text first
        if self.TEXT_CACHE_PATH.exists():
            try:
                cached = json.loads(self.TEXT_CACHE_PATH.read_text())
                self._full_text = cached.get('text', '')
                if self._full_text:
                    return self._full_text
            except Exception:
                pass
        
        pdf_path = self.fetch_pdf()
        text_parts = []
        started = False
        
        if HAS_PDFPLUMBER:
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        # Start extracting from the enacting clause
                        if not started and 'HER MAJESTY, by and with the advice and consent' in page_text:
                            started = True
                        if started:
                            text_parts.append(page_text)
        elif HAS_PYPDF2:
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        if not started and 'HER MAJESTY, by and with the advice and consent' in page_text:
                            started = True
                        if started:
                            text_parts.append(page_text)
        else:
            raise RuntimeError("Neither pdfplumber nor PyPDF2 is installed")
        
        # Join pages with double newline, no page markers
        self._full_text = "\n\n".join(text_parts)
        
        # Cache extracted text
        self.TEXT_CACHE_PATH.write_text(json.dumps({
            'text': self._full_text,
            'source_url': self.SOURCE_URL,
            'pdf_hash': hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:16]
        }))
        
        return self._full_text
    
    def parse_sections(self) -> Dict[str, str]:
        """Parse act into sections by section number."""
        if self._parsed:
            return self._sections
        
        text = self.extract_text()
        
        # Split by page markers and find section headers
        # Pattern: "Section N" or "N(1)" at start of line, or just "(1)" for subsections
        lines = text.split('\n')
        current_section = None
        current_content = []
        current_parent_section = None  # Track parent section for subsections like "(2)"
        
        # Pattern to detect running headers (appear on every page)
        # Headers may be split across lines: "CHILD, YOUT H AND FAMILY RSA 2000" + "Section 1 ..."
        running_header_line1 = re.compile(r'CHILD,\s*YOUT\s*H\s*AND\s*FAMILY\s+RSA\s+\d{4}')
        running_header_line2 = re.compile(r'Section\s+\d+.*ENHANC\s*EMENT\s+ACT\s+Chapter\s+C-12')
        
        # Section header patterns - more restrictive to avoid matching internal references
        # Real section headers: "1(1) In this Act", "(2) For the purposes", "2(1) If a child"
        # References to avoid: "122(2) of this Act", "section 122(2)", etc.
        section_header_pattern = re.compile(
            r'^\s*(?:Section\s+)?(\d+(?:\.\d+)?)(?:\((\d+)\))?\s+(?:In|If|For|Where|When|Subject|Notwithstanding|Despite|Every|Any|A|The|No)'
        )
        subsection_header_pattern = re.compile(r'^\s*\((\d+)\)\s+(?:For|Where|If|The|A|An|In|Subject|Notwithstanding)')
        rsa_header_pattern = re.compile(r'RSA 2000\s+Section\s+(\d+(?:\.\d+)?)')
        
        for i, line in enumerate(lines):
            # Skip running headers (may span 2 lines)
            if running_header_line1.search(line):
                # Check if next line is the second part
                if i + 1 < len(lines) and running_header_line2.search(lines[i + 1]):
                    continue
                continue
            if running_header_line2.search(line):
                # Check if previous line was the first part
                if i > 0 and running_header_line1.search(lines[i - 1]):
                    continue
                continue
            
            # Skip standalone page numbers
            if re.match(r'^\s*\d+\s*$', line):
                continue
            
            # Match section headers using restrictive patterns
            section_match = section_header_pattern.match(line)
            # Match subsection-only headers like "(2) For the purposes"
            subsection_match = subsection_header_pattern.match(line)
            # Also match "RSA 2000 Section N Chapter C-12" pattern
            rsa_match = rsa_header_pattern.match(line)
            
            if section_match:
                # Save previous section
                if current_section and current_content:
                    self._sections[current_section] = '\n'.join(current_content).strip()
                # Start new section
                sec_num = section_match.group(1)
                subsec = section_match.group(2)
                current_parent_section = sec_num
                current_section = f"{sec_num}" + (f"({subsec})" if subsec else "")
                current_content = [line]
            elif subsection_match and current_parent_section:
                # Subsection like "(2)" - prepend parent section number
                # Save previous subsection
                if current_section and current_content:
                    self._sections[current_section] = '\n'.join(current_content).strip()
                subsec = subsection_match.group(1)
                current_section = f"{current_parent_section}({subsec})"
                current_content = [line]
            elif rsa_match:
                # RSA header - might indicate section start
                sec_num = rsa_match.group(1)
                if current_section and current_content:
                    self._sections[current_section] = '\n'.join(current_content).strip()
                current_parent_section = sec_num
                current_section = sec_num
                current_content = [line]
            else:
                if current_section:
                    current_content.append(line)
        
        # Save last section
        if current_section and current_content:
            self._sections[current_section] = '\n'.join(current_content).strip()
        
        self._parsed = True
        return self._sections
    
    def get_section(self, section_ref: str) -> Optional[str]:
        """Get verbatim text of a section by reference (e.g., '1', '1(2)', '2(1)')."""
        sections = self.parse_sections()
        
        # Normalize reference
        section_ref = section_ref.strip()
        
        # Try exact match
        if section_ref in sections:
            return sections[section_ref]
        
        # Try with/without parentheses
        if '(' not in section_ref:
            # Look for section with subsections
            for key in sections:
                if key.startswith(section_ref + '('):
                    return sections[key]
        
        # Fuzzy match - find section containing the reference
        for key, content in sections.items():
            if key.startswith(section_ref) or section_ref in key:
                return content
        
        return None
    
    def search(self, keyword: str, context_lines: int = 3) -> List[Dict[str, Any]]:
        """Search for keyword in the act, return matches with context."""
        text = self.extract_text()
        keyword_lower = keyword.lower()
        results = []
        
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if keyword_lower in line.lower():
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                context = '\n'.join(lines[start:end])
                # Find section this belongs to
                section = self._find_section_for_line(i, lines)
                results.append({
                    'line_number': i + 1,
                    'section': section,
                    'context': context,
                    'match_line': line.strip()
                })
        
        return results
    
    def _find_section_for_line(self, line_idx: int, lines: List[str]) -> Optional[str]:
        """Find which section a line number belongs to."""
        # Search backwards for section header
        for i in range(line_idx, -1, -1):
            match = re.match(r'^\s*(?:Section\s+)?(\d+(?:\.\d+)?)(?:\((\d+)\))?\s', lines[i])
            if match and not re.match(r'RSA 2000\s+Section\s+', lines[i]):
                sec_num = match.group(1)
                subsec = match.group(2)
                return f"{sec_num}" + (f"({subsec})" if subsec else "")
            rsa_match = re.match(r'RSA 2000\s+Section\s+(\d+(?:\.\d+)?)', lines[i])
            if rsa_match:
                return rsa_match.group(1)
        return None
    
    def get_key_sections(self) -> Dict[str, str]:
        """Return the three key sections required."""
        return {
            'definition_child_in_need': self.get_section('1(2)') or '',
            'grounds_for_intervention': self.get_section('1(2)') or '',  # Same section, grounds are in 1(2)(a)-(h)
            'best_interests_test': self.get_section('2(1)') or '',
        }


def main():
    parser = argparse.ArgumentParser(
        description='Alberta CYFEA (RSA 2000, c C-12) - Section lookup and search',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.youth_protection.ab_cyfea 1(2)
  python -m scripts.youth_protection.ab_cyfea 2(1)
  python -m scripts.youth_protection.ab_cyfea --search "child in need"
  python -m scripts.youth_protection.ab_cyfea --search "best interests"
  python -m scripts.youth_protection.ab_cyfea --key-sections
        """
    )
    parser.add_argument('section', nargs='?', help='Section reference (e.g., 1, 1(2), 2(1))')
    parser.add_argument('--search', '-s', help='Search keyword')
    parser.add_argument('--key-sections', '-k', action='store_true', 
                        help='Print the three key sections: definition of child in need, grounds for intervention, best interests test')
    parser.add_argument('--fetch', '-f', action='store_true', help='Force re-fetch PDF')
    parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    adapter = ABCYFEAAdapter()
    
    if args.fetch:
        adapter.fetch_pdf(force=True)
        print("PDF re-fetched and cached.")
        return
    
    if args.key_sections:
        sections = adapter.get_key_sections()
        if args.json:
            print(json.dumps(sections, indent=2))
        else:
            for name, text in sections.items():
                print(f"\n{'='*60}")
                print(f"{name.upper().replace('_', ' ')}")
                print(f"{'='*60}")
                print(text[:5000] + ("..." if len(text) > 5000 else ""))
        return
    
    if args.search:
        results = adapter.search(args.search)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} matches for '{args.search}':\n")
            for r in results[:20]:  # Limit to 20 results
                print(f"--- Section {r['section'] or '?'} (line {r['line_number']}) ---")
                print(r['context'])
                print()
            if len(results) > 20:
                print(f"... and {len(results) - 20} more matches")
        return
    
    if args.section:
        text = adapter.get_section(args.section)
        if text:
            if args.json:
                print(json.dumps({'section': args.section, 'text': text}, indent=2))
            else:
                print(text)
        else:
            print(f"Section '{args.section}' not found", file=sys.stderr)
            sys.exit(1)
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()