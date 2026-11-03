"""
Nova Scotia Children and Family Services Act (SNS 1990, c 5) Parser

Verbatim statute parser for the official nslegislature.ca source.
Source: https://nslegislature.ca/sites/default/files/legc/statutes/children%20and%20family%20services%20act.pdf
HTML: https://nslegislature.ca/sites/default/files/legc/statutes%20HTML/children%20and%20family%20services.htm

Key sections verified from official source:
- Section 1: Short title
- Section 2: Purpose and paramount consideration
- Section 3: Interpretation (definitions)
- Section 4: Minister's supervision and court appearance
- Sections 5-14: Administration and agencies
- Sections 15-31: Child protection proceedings
- Sections 32-48: Court orders (interim, temporary, permanent care)
- Sections 49-53: Appeals
- Sections 54-60: Adoption (proclaimed Dec 8, 2003)
- Section 73: Adoption (NOT proclaimed)
- Sections 62-66: Child Abuse Register
- Sections 67-72: Adoption agreements
- Sections 74-85: Adoption orders
- Sections 86-98: Offences and penalties
- Sections 99-100: Repeals
- Sections 101-108: Consequential amendments
- Section 109: Effective date and proclamation

Amendment history tracked: 1994-95, c.7; 1996, c.3; 1996, c.10; 2001, c.3; 2002, c.5; 2005, c.15; 2008, c.12; 2015, c.37; 2015, c.44; 2018, c.33; 2021, c.1; 2026, c.4
"""

import re
import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Iterator
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import pdfplumber
from io import BytesIO


@dataclass
class StatuteSection:
    """Represents a single section of the statute with full hierarchy."""
    number: str
    title: Optional[str]
    text: str
    subsections: Dict[str, 'StatuteSection'] = field(default_factory=dict)
    clauses: Dict[str, str] = field(default_factory=dict)
    amendment_notes: List[str] = field(default_factory=list)
    source_line_start: int = 0
    source_line_end: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'number': self.number,
            'title': self.title,
            'text': self.text,
            'subsections': {k: v.to_dict() for k, v in self.subsections.items()},
            'clauses': self.clauses,
            'amendment_notes': self.amendment_notes,
            'source_line_start': self.source_line_start,
            'source_line_end': self.source_line_end,
        }
    
    def get_full_text(self, include_subsections: bool = True) -> str:
        """Get concatenated text of this section and optionally subsections."""
        parts = [self.text]
        if include_subsections:
            for sub in sorted(self.subsections.values(), key=lambda s: s.number):
                parts.append(sub.get_full_text(include_subsections))
        return '\n'.join(parts)


@dataclass
class CFSAStatute:
    """Complete parsed Children and Family Services Act."""
    citation: str = "SNS 1990, c 5"
    short_title: str = "Children and Family Services Act"
    long_title: str = "An Act Respecting Services to Children and their Families, the Protection of Children and Adoption"
    sections: Dict[str, StatuteSection] = field(default_factory=dict)
    preamble: str = ""
    amendment_history: List[str] = field(default_factory=list)
    proclamation_notes: Dict[str, str] = field(default_factory=dict)
    source_url: str = "https://nslegislature.ca/sites/default/files/legc/statutes/children%20and%20family%20services%20act.pdf"
    source_hash: str = ""
    parsed_at: str = ""
    
    def get_section(self, number: str) -> Optional[StatuteSection]:
        """Get section by number (e.g., '15', '15(1)', '15(1)(a)')."""
        if '(' not in number:
            return self.sections.get(number)
        # Handle subsection/clause lookup
        main_num = number.split('(')[0]
        section = self.sections.get(main_num)
        if not section:
            return None
        # Navigate subsection path
        path = re.findall(r'\(([^)]+)\)', number)
        current = section
        for part in path:
            if part in current.subsections:
                current = current.subsections[part]
            elif part in current.clauses:
                return StatuteSection(number=number, title=None, text=current.clauses[part])
            else:
                return None
        return current
    
    def search(self, pattern: str, case_sensitive: bool = False) -> List[StatuteSection]:
        """Search sections for text pattern."""
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
        results = []
        for section in self.sections.values():
            if regex.search(section.get_full_text()):
                results.append(section)
        return results
    
    def iter_sections(self) -> Iterator[StatuteSection]:
        """Iterate all sections in order."""
        for num in sorted(self.sections.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            yield self.sections[num]
    
    def to_json(self, path: Optional[str] = None) -> str:
        """Export full statute as JSON."""
        data = {
            'citation': self.citation,
            'short_title': self.short_title,
            'long_title': self.long_title,
            'preamble': self.preamble,
            'amendment_history': self.amendment_history,
            'proclamation_notes': self.proclamation_notes,
            'source_url': self.source_url,
            'source_hash': self.source_hash,
            'parsed_at': self.parsed_at,
            'sections': {k: v.to_dict() for k, v in self.sections.items()},
        }
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        if path:
            Path(path).write_text(json_str, encoding='utf-8')
        return json_str
    
    @classmethod
    def from_json(cls, path: str) -> 'CFSAStatute':
        """Load statute from JSON export."""
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        statute = cls(
            citation=data['citation'],
            short_title=data['short_title'],
            long_title=data['long_title'],
            preamble=data['preamble'],
            amendment_history=data['amendment_history'],
            proclamation_notes=data['proclamation_notes'],
            source_url=data['source_url'],
            source_hash=data['source_hash'],
            parsed_at=data['parsed_at'],
        )
        for num, sec_data in data['sections'].items():
            statute.sections[num] = cls._dict_to_section(sec_data)
        return statute
    
    @staticmethod
    def _dict_to_section(data: Dict) -> StatuteSection:
        section = StatuteSection(
            number=data['number'],
            title=data['title'],
            text=data['text'],
            clauses=data['clauses'],
            amendment_notes=data['amendment_notes'],
            source_line_start=data['source_line_start'],
            source_line_end=data['source_line_end'],
        )
        for sub_num, sub_data in data['subsections'].items():
            section.subsections[sub_num] = CFSAStatute._dict_to_section(sub_data)
        return section


class CFSAParser:
    """Parser for the Nova Scotia Children and Family Services Act."""
    
    PDF_URL = "https://nslegislature.ca/sites/default/files/legc/statutes/children%20and%20family%20services%20act.pdf"
    HTML_URL = "https://nslegislature.ca/sites/default/files/legc/statutes%20HTML/children%20and%20family%20services.htm"
    
    # Known amendment acts from official source
    AMENDMENT_HISTORY = [
        "1994-95, c. 7, ss. 11-15, 150",
        "1996, c. 3, ss. 37, 38",
        "1996, c. 10",
        "2001, c. 3, s. 4",
        "2002, c. 5, ss. 2, 3",
        "2005, c. 15",
        "2008, c. 12",
        "2015, c. 37 (except s. 33(2))",
        "2015, c. 44, ss. 49-52",
        "2018, c. 33, s. 17",
        "2021, c. 1, s. 48",
        "2026, c. 4, s. 6",
    ]
    
    PROCLAMATION_NOTES = {
        "1-53, 61-72, 74-108": "In force September 3, 1991",
        "54-60": "Proclaimed December 4, 2003; in force December 8, 2003",
        "73": "NOT proclaimed in force",
    }
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._raw_text: str = ""
        self._lines: List[str] = []
    
    def fetch_pdf(self) -> bytes:
        """Download the official PDF from nslegislature.ca."""
        req = Request(self.PDF_URL, headers={'User-Agent': 'Mozilla/5.0 CFSA-Parser/1.0'})
        with urlopen(req, timeout=self.timeout) as resp:
            return resp.read()
    
    def fetch_html(self) -> str:
        """Download the official HTML version from nslegislature.ca."""
        req = Request(self.HTML_URL, headers={'User-Agent': 'Mozilla/5.0 CFSA-Parser/1.0'})
        with urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF using pdfplumber."""
        text_parts = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return '\n'.join(text_parts)
    
    def extract_text_from_html(self, html: str) -> str:
        """Extract text from HTML version (simpler structure)."""
        from html import unescape
        # Remove script/style
        html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Convert block elements to newlines
        html = re.sub(r'</(p|div|h[1-6]|li|br|tr|td|th)>', '\n', html, flags=re.IGNORECASE)
        # Remove remaining tags
        html = re.sub(r'<[^>]+>', '', html)
        # Unescape entities
        text = unescape(html)
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    
    def parse(self, source: str = "pdf") -> CFSAStatute:
        """Parse the statute from official source."""
        if source == "pdf":
            pdf_bytes = self.fetch_pdf()
            self._raw_text = self.extract_text_from_pdf(pdf_bytes)
            self._compute_source_hash(pdf_bytes)
        elif source == "html":
            html = self.fetch_html()
            self._raw_text = self.extract_text_from_html(html)
            self._compute_source_hash(html.encode('utf-8'))
        else:
            raise ValueError("source must be 'pdf' or 'html'")
        
        self._lines = self._raw_text.split('\n')
        return self._parse_structure()
    
    def _compute_source_hash(self, content: bytes):
        self._source_hash = hashlib.sha256(content).hexdigest()[:16]
    
    def _parse_structure(self) -> CFSAStatute:
        """Parse the raw text into structured statute."""
        statute = CFSAStatute(
            source_hash=self._source_hash,
            parsed_at=self._current_timestamp(),
        )
        statute.amendment_history = self.AMENDMENT_HISTORY.copy()
        statute.proclamation_notes = self.PROCLAMATION_NOTES.copy()
        
        # Parse preamble (everything before Section 1)
        preamble_end = self._find_section_start(1)
        if preamble_end > 0:
            statute.preamble = '\n'.join(self._lines[:preamble_end]).strip()
        
        # Parse sections 1-109
        current_section_num = 1
        while current_section_num <= 109:
            section = self._parse_section(current_section_num)
            if section:
                statute.sections[str(current_section_num)] = section
                current_section_num = self._find_next_section(current_section_num)
            else:
                current_section_num += 1
        
        return statute
    
    def _current_timestamp(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    
    def _find_section_start(self, section_num: int) -> int:
        """Find line index where a section starts."""
        patterns = [
            rf'^\s*{section_num}\s+',  # "1 Short title"
            rf'^\s*{section_num}\.',   # "1. Short title"
            rf'^\*\*{section_num}\s+', # "**1 Short title"
            rf'^\*\*{section_num}\.',  # "**1. Short title"
        ]
        for i, line in enumerate(self._lines):
            for pattern in patterns:
                if re.match(pattern, line):
                    return i
        return -1
    
    def _find_next_section(self, current_num: int) -> int:
        """Find the next section number after current."""
        start = self._find_section_start(current_num)
        if start == -1:
            return current_num + 1
        for i in range(start + 1, len(self._lines)):
            match = re.match(r'^\s*(\d{1,3})\s', self._lines[i])
            if match:
                next_num = int(match.group(1))
                if next_num > current_num:
                    return next_num
        return current_num + 1
    
    def _parse_section(self, section_num: int) -> Optional[StatuteSection]:
        """Parse a single section with all subsections and clauses."""
        start = self._find_section_start(section_num)
        if start == -1:
            return None
        
        end = self._find_section_start(section_num + 1)
        if end == -1:
            end = len(self._lines)
        
        section_lines = self._lines[start:end]
        if not section_lines:
            return None
        
        # Parse section header
        header_line = section_lines[0]
        title = self._extract_section_title(header_line, section_num)
        
        # Parse body
        body_lines = section_lines[1:]
        text, subsections, clauses, amendment_notes = self._parse_section_body(body_lines)
        
        return StatuteSection(
            number=str(section_num),
            title=title,
            text=text,
            subsections=subsections,
            clauses=clauses,
            amendment_notes=amendment_notes,
            source_line_start=start,
            source_line_end=end,
        )
    
    def _extract_section_title(self, header_line: str, section_num: int) -> Optional[str]:
        """Extract section title from header line."""
        # Patterns: "1 Short title", "2 (1) Purpose...", "**1 Short title"
        patterns = [
            rf'^\*\*{section_num}\s+(.+)$',
            rf'^\s*{section_num}\s+(.+)$',
            rf'^\s*{section_num}\.\s+(.+)$',
        ]
        for pattern in patterns:
            match = re.match(pattern, header_line)
            if match:
                title = match.group(1).strip()
                # Remove trailing citation like "1990, c. 5, s. 1."
                title = re.sub(r'\s+\d{4}, c\.\s*\d+, s\.\s*\d+\.?$', '', title)
                return title if title else None
        return None
    
    def _parse_section_body(self, lines: List[str]) -> tuple:
        """Parse section body into text, subsections, clauses, amendments."""
        text_parts = []
        subsections = {}
        clauses = {}
        amendment_notes = []
        
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            
            # Skip empty lines
            if not line.strip():
                i += 1
                continue
            
            # Check for amendment note
            amend_match = re.match(r'^\s*\d{4}, c\.\s*\d+, s\.\s*\d+\.?', line)
            if amend_match:
                amendment_notes.append(line.strip())
                i += 1
                continue
            
            # Check for subsection: "(1)", "(2)", etc.
            sub_match = re.match(r'^\s*\((\d+)\)\s*(.*)$', line)
            if sub_match:
                sub_num = sub_match.group(1)
                sub_text = sub_match.group(2).strip()
                # Collect subsection content
                sub_lines = [sub_text] if sub_text else []
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip()
                    # Stop at next subsection, clause, or section
                    if re.match(r'^\s*\(\d+\)\s', next_line):
                        break
                    if re.match(r'^\s*[a-z]\)\s', next_line):
                        break
                    if re.match(r'^\s*\d{1,3}\s', next_line) and not re.match(r'^\s*\d{1,3}\s+[A-Z]', next_line):
                        # Might be next section - check if it's a clause continuation
                        break
                    if next_line.strip():
                        sub_lines.append(next_line)
                    i += 1
                
                # Parse clauses within subsection
                sub_full_text = '\n'.join(sub_lines).strip()
                sub_clauses = self._parse_clauses(sub_full_text)
                if sub_clauses:
                    clauses.update({f"({sub_num}){k}": v for k, v in sub_clauses.items()})
                    # Keep subsection text without clauses
                    sub_text_clean = self._remove_clauses(sub_full_text, sub_clauses)
                else:
                    sub_text_clean = sub_full_text
                
                subsections[f"({sub_num})"] = StatuteSection(
                    number=f"({sub_num})",
                    title=None,
                    text=sub_text_clean,
                    clauses=sub_clauses,
                    source_line_start=0,
                    source_line_end=0,
                )
                continue
            
            # Regular text
            text_parts.append(line)
            i += 1
        
        # Parse top-level clauses
        full_text = '\n'.join(text_parts).strip()
        top_clauses = self._parse_clauses(full_text)
        if top_clauses:
            clauses.update(top_clauses)
            full_text = self._remove_clauses(full_text, top_clauses)
        
        return full_text, subsections, clauses, amendment_notes
    
    def _parse_clauses(self, text: str) -> Dict[str, str]:
        """Extract clauses like (a), (b), (i), (ii) from text."""
        clauses = {}
        # Pattern for clauses: (a), (b), (i), (ii), etc.
        clause_pattern = r'\(([a-z]|[ivx]+)\)\s*([^\(]+?)(?=\s*\([a-zivx]+\)|$)'
        for match in re.finditer(clause_pattern, text, re.DOTALL):
            clause_id = f"({match.group(1)})"
            clause_text = match.group(2).strip()
            if clause_text:
                clauses[clause_id] = clause_text
        return clauses
    
    def _remove_clauses(self, text: str, clauses: Dict[str, str]) -> str:
        """Remove clause text from parent text."""
        result = text
        for clause_id, clause_text in clauses.items():
            # Remove the clause pattern
            pattern = re.escape(clause_id) + r'\s*' + re.escape(clause_text)
            result = re.sub(pattern, '', result, flags=re.DOTALL)
        # Clean up extra whitespace
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()


def load_statute(source: str = "pdf", cache_path: Optional[str] = None) -> CFSAStatute:
    """
    Convenience function to load the statute.
    
    Args:
        source: "pdf" or "html" - which official source to use
        cache_path: Optional path to cache/load JSON export
    
    Returns:
        CFSAStatute object with full parsed structure
    """
    if cache_path and Path(cache_path).exists():
        return CFSAStatute.from_json(cache_path)
    
    parser = CFSAParser()
    statute = parser.parse(source)
    
    if cache_path:
        statute.to_json(cache_path)
    
    return statute


if __name__ == "__main__":
    # Demo: parse and show key sections
    print("Parsing Nova Scotia Children and Family Services Act...")
    try:
        statute = load_statute(source="html")  # HTML is more reliable
        
        print(f"\n=== {statute.short_title} ({statute.citation}) ===")
        print(f"Long title: {statute.long_title}")
        print(f"Sections parsed: {len(statute.sections)}")
        print(f"Source: {statute.source_url}")
        print(f"Source hash: {statute.source_hash}")
        print(f"Amendment history: {len(statute.amendment_history)} acts")
        
        # Show key sections
        key_sections = ['1', '2', '3', '4', '15', '20', '32', '47', '49', '62', '63', '73', '83', '109']
        print("\n--- Key Sections ---")
        for num in key_sections:
            sec = statute.get_section(num)
            if sec:
                title = sec.title or "(no title)"
                preview = sec.text[:120].replace('\n', ' ') + "..." if len(sec.text) > 120 else sec.text
                print(f"  s.{num}: {title}")
                print(f"    {preview}")
                if sec.subsections:
                    print(f"    Subsections: {list(sec.subsections.keys())}")
        
        # Search demo
        print("\n--- Search: 'best interests of the child' ---")
        results = statute.search(r'best interests of the child')
        print(f"Found in {len(results)} sections:")
        for sec in results[:5]:
            print(f"  s.{sec.number}")
        
        # Export to JSON
        output_path = "/home/rightguy/ns_cfsa_parsed.json"
        statute.to_json(output_path)
        print(f"\nExported to {output_path}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()