"""
Table 4 Parser: Parses extracted text and table structures from PAIMANA Table 4 / All Ongoing Projects.
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def clean_number(val: Any) -> Optional[float]:
    """Clean and parse a numeric value, stripping currency, commas, and parentheses."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str in ['-', '(-)', '–', '—', 'nan', 'null', 'None']:
        return None
    # Remove currency signs, commas, extra whitespace
    cleaned = re.sub(r'[₹,\s]', '', val_str)
    # Check if enclosed in parentheses for revised values (e.g. '(265.91)')
    m = re.match(r'^\(?([0-9]+(?:\.[0-9]+)?)\)?$', cleaned)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date_mmyyyy(date_str: Any) -> Optional[str]:
    """Parse date string into YYYY-MM-01 format."""
    if date_str is None:
        return None
    date_str = str(date_str).strip()
    if not date_str or date_str in ['-', '(-)', '–', '—', 'nan', 'null', 'None']:
        return None
    
    # Remove wrapping parens if any
    date_str = date_str.strip('()')
    
    # MM/YYYY or MM-YYYY
    m = re.search(r'(\d{1,2})[/\-](\d{4})', date_str)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1900 <= year <= 2100:
            return f"{year:04d}-{month:02d}-01"

    # YYYY-MM-DD
    m = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', date_str)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1900 <= year <= 2100:
            return f"{year:04d}-{month:02d}-01"

    return None


def pop_trailing_paren(s: str) -> Tuple[str, Optional[str]]:
    """
    Pops the outermost balanced trailing parenthesized expression from s, if one exists.
    Returns (remaining_string, popped_token_content).
    """
    s = s.strip()
    if not s.endswith(')'):
        return s, None
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ')':
            depth += 1
        elif s[i] == '(':
            depth -= 1
            if depth == 0:
                token = s[i+1:-1].strip()
                remainder = s[:i].strip()
                return remainder, token
    return s, None


class Table4Parser:
    """Parses Table 4 pages from PDF extractor and outputs raw project records."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def parse_project_cell(self, cell_text: str) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Parse the multi-line or inline Project Name cell into:
        (project_name, agency, project_code, legacy_ocms_code, pmgid)
        Handles trailing (Agency), (Project Code), (OCMS) (PMGID) even when nested or concatenated.
        """
        if not cell_text:
            return "", None, None, None, None
            
        lines = [line.strip() for line in str(cell_text).split('\n') if line.strip()]
        if not lines:
            return "", None, None, None, None

        project_code = None
        legacy_ocms = None
        pmgid = None
        agency = None

        idx = len(lines) - 1

        # 1. Check for [LEGACY OCMS CODE] [PMGID] on the last line(s)
        # E.g. '(N16000437) (10000)' or '(-) (10000)' or '(N16000437) (-)' or '(-) (-)'
        if idx >= 0:
            line = lines[idx]
            m_dual = re.match(r'^\(([^)]*)\)\s+\(([^)]*)\)$', line)
            if m_dual:
                c1, c2 = m_dual.group(1).strip(), m_dual.group(2).strip()
                legacy_ocms = c1 if c1 and c1 not in ['-', '—', '–', 'none', 'null', '(-)','NaN'] else None
                pmgid = c2 if c2 and c2 not in ['-', '—', '–', 'none', 'null', '(-)','NaN'] else None
                idx -= 1
            else:
                m_single_ocms = re.match(r'^\((N\d{7,9}|[A-Z]\d{7,9}|\d{8,9})\)$', line)
                m_dash_dual = re.match(r'^\([-—–]\)\s*\([-—–]\)$', line)
                if m_single_ocms:
                    legacy_ocms = m_single_ocms.group(1).strip()
                    idx -= 1
                elif m_dash_dual:
                    idx -= 1

        # 2. Check for standalone Project Code on current line: e.g. '(617830)' or '617830'
        if idx >= 0:
            line = lines[idx]
            m_code = re.match(r'^\((\d{4,7})\)$', line)
            m_code2 = re.match(r'^(\d{5,7})$', line)
            if m_code:
                project_code = m_code.group(1)
                idx -= 1
            elif m_code2:
                project_code = m_code2.group(1)
                idx -= 1

        # 3. Check for standalone Agency on current line using balanced parentheses: e.g. '(Central Railway (CR) - II)'
        if idx >= 0:
            line = lines[idx]
            rem, tok = pop_trailing_paren(line)
            if tok is not None and not rem:
                if not re.match(r'^\d+$', tok) and not re.match(r'^(N\d{7,9}|[A-Z]\d{7,9})$', tok):
                    agency = tok
                    idx -= 1

        # 4. Now process remaining lines: they may still contain trailing (Agency) and/or (Project Code) concatenated
        remaining_text = " ".join(lines[:idx + 1]).strip()
        curr = remaining_text
        while True:
            curr_stripped = curr.rstrip()
            curr_next, tok = pop_trailing_paren(curr_stripped)
            if tok is None:
                break
            
            t = tok.strip()
            # Check if t is 8-9 digit OCMS code
            if not legacy_ocms and (re.match(r'^(N\d{7,9}|[A-Z]\d{7,9})$', t) or re.match(r'^\d{8,9}$', t)):
                legacy_ocms = t
                curr = curr_next
                continue
            # Check if t is Project Code (e.g. 617926)
            elif not project_code and re.match(r'^\d{5,7}$', t):
                project_code = t
                curr = curr_next
                continue
            elif not project_code and re.match(r'^\d{4}$', t):
                project_code = t
                curr = curr_next
                continue
            # Check if t is PMGID
            elif not pmgid and re.match(r'^\d{1,5}$', t):
                pmgid = t
                curr = curr_next
                continue
            # Check if t is Agency (if agency not yet found and t has alphabets)
            elif not agency and any(c.isalpha() for c in t) and t not in ['-', '—', '–', 'none', 'null', 'NaN', '(-)']:
                agency = t
                curr = curr_next
                continue
            else:
                break

        project_name = curr.strip()
        if not project_name and lines:
            project_name = lines[0]

        # Clean multiple spaces inside project_name
        project_name = re.sub(r'\s+', ' ', project_name)

        return project_name, agency, project_code, legacy_ocms, pmgid

    def parse_pages(self, extracted_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse raw table pages into structured project records.
        """
        pages_data = extracted_data.get("pages_data", [])
        report_month = extracted_data.get("report_month")
        source_report = extracted_data.get("source_report", "unknown.pdf")

        current_ministry = None
        current_sector = None
        raw_records = []

        for page_info in pages_data:
            page_num = page_info["page_number"]
            table_rows = page_info.get("table_rows", [])

            if table_rows:
                ministry, sector, recs = self._process_table_rows(
                    table_rows, current_ministry, current_sector, page_num, source_report, report_month
                )
                current_ministry = ministry
                current_sector = sector
                raw_records.extend(recs)
            else:
                text = page_info.get("text", "")
                ministry, sector, recs = self._process_text_layout(
                    text, current_ministry, current_sector, page_num, source_report, report_month
                )
                current_ministry = ministry
                current_sector = sector
                raw_records.extend(recs)

        logger.info(f"Successfully extracted {len(raw_records)} project records across {len(pages_data)} pages.")
        return raw_records

    def _process_table_rows(self, rows: List[List[Any]], current_ministry: Optional[str],
                            current_sector: Optional[str], page_num: int, source_report: str,
                            report_month: str) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
        """Process rows returned from table extractors."""
        records = []
        for row in rows:
            if not row or not any(row):
                continue
            
            row_cells = [str(c).strip() if c is not None else "" for c in row]
            first_cell = row_cells[0]
            joined_row = " ".join(row_cells)

            # Check if row is a repeated header
            if re.search(r'Sl\.?\s*No', first_cell, re.IGNORECASE) or \
               re.search(r'Project\s*Name', joined_row, re.IGNORECASE) and re.search(r'Physical\s*Progress', joined_row, re.IGNORECASE):
                continue

            # Check for category totals e.g. "Total (27)", "Total (118)"
            if re.search(r'Total\s*\(\d+\)', joined_row, re.IGNORECASE):
                continue

            # Check for Ministry / Department header row
            if re.match(r'^(Ministry\s+of|Department\s+of|Department\s+for)\b', first_cell, re.IGNORECASE) or \
               (len(row_cells) > 1 and re.match(r'^(Ministry\s+of|Department\s+of|Department\s+for)\b', row_cells[1], re.IGNORECASE)):
                current_ministry = first_cell if re.match(r'^(Ministry|Department)', first_cell) else row_cells[1]
                continue

            # Check for Sector header row
            non_empty = [c for c in row_cells if c]
            if len(non_empty) == 1 and not first_cell.isdigit():
                candidate = non_empty[0]
                if not re.search(r'Total\b', candidate, re.IGNORECASE) and not re.search(r'\d{5,}', candidate):
                    current_sector = candidate
                    continue

            # Check if this is a project row:
            sl_no_match = re.match(r'^(\d+)$', first_cell)
            is_project_cell = bool(re.search(r'\(\d{4,7}\)', first_cell)) or (len(row_cells) > 1 and bool(re.search(r'\(\d{4,7}\)', row_cells[1])))

            if sl_no_match and len(row_cells) >= 5:
                sl_no_val = int(sl_no_match.group(1))
                project_raw = row_cells[1]
                project_name, agency, project_code, legacy_ocms, pmgid = self.parse_project_cell(project_raw)
                
                state = row_cells[2] if len(row_cells) > 2 else ""
                approval_str = row_cells[3] if len(row_cells) > 3 else ""
                approval_start = parse_date_mmyyyy(approval_str)

                doc_str = row_cells[4] if len(row_cells) > 4 else ""
                orig_doc, rev_doc = self._parse_dual_doc(doc_str)

                cost_str = row_cells[5] if len(row_cells) > 5 else ""
                orig_cost, rev_cost = self._parse_dual_cost(cost_str)

                expenditure_str = row_cells[6] if len(row_cells) > 6 else ""
                cum_exp = clean_number(expenditure_str)

                progress_str = row_cells[7] if len(row_cells) > 7 else (row_cells[6] if len(row_cells) == 7 else "")
                physical_progress = clean_number(progress_str)

                if rev_cost is None and orig_cost is not None:
                    rev_cost = orig_cost

                # project_id and project_key are strictly the Project Code
                proj_id = project_code if project_code else f"PROJ_{sl_no_val}"

                rec = {
                    "sl_no": sl_no_val,
                    "project_id": proj_id,
                    "project_key": proj_id,
                    "project_name": project_name,
                    "agency": agency,
                    "pmgid": pmgid,
                    "legacy_ocms_code": legacy_ocms,
                    "ministry_department": current_ministry,
                    "sector": current_sector,
                    "state": state,
                    "report_month": report_month,
                    "approval_start": approval_start,
                    "original_target_doc": orig_doc,
                    "revised_doc": rev_doc,
                    "original_cost_crore": orig_cost,
                    "revised_cost_crore": rev_cost,
                    "cumulative_expenditure_crore": cum_exp,
                    "physical_progress_pct": physical_progress,
                    "page": page_num,
                    "source_report": source_report
                }
                records.append(rec)

            elif is_project_cell and len(row_cells) >= 4:
                project_name, agency, project_code, legacy_ocms, pmgid = self.parse_project_cell(first_cell)
                state = row_cells[1] if len(row_cells) > 1 else ""
                approval_str = row_cells[2] if len(row_cells) > 2 else ""
                approval_start = parse_date_mmyyyy(approval_str)

                doc_str = row_cells[3] if len(row_cells) > 3 else ""
                orig_doc, rev_doc = self._parse_dual_doc(doc_str)

                cost_str = row_cells[4] if len(row_cells) > 4 else ""
                orig_cost, rev_cost = self._parse_dual_cost(cost_str)

                expenditure_str = row_cells[5] if len(row_cells) > 5 else ""
                cum_exp = clean_number(expenditure_str)

                progress_str = row_cells[6] if len(row_cells) > 6 else ""
                physical_progress = clean_number(progress_str)

                if rev_cost is None and orig_cost is not None:
                    rev_cost = orig_cost

                proj_id = project_code if project_code else f"PROJ_{len(records)+1}"

                rec = {
                    "sl_no": len(records) + 1,
                    "project_id": proj_id,
                    "project_key": proj_id,
                    "project_name": project_name,
                    "agency": agency,
                    "pmgid": pmgid,
                    "legacy_ocms_code": legacy_ocms,
                    "ministry_department": current_ministry,
                    "sector": current_sector,
                    "state": state,
                    "report_month": report_month,
                    "approval_start": approval_start,
                    "original_target_doc": orig_doc,
                    "revised_doc": rev_doc,
                    "original_cost_crore": orig_cost,
                    "revised_cost_crore": rev_cost,
                    "cumulative_expenditure_crore": cum_exp,
                    "physical_progress_pct": physical_progress,
                    "page": page_num,
                    "source_report": source_report
                }
                records.append(rec)

        return current_ministry, current_sector, records

    def _process_text_layout(self, text: str, current_ministry: Optional[str],
                             current_sector: Optional[str], page_num: int, source_report: str,
                             report_month: str) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
        """Fallback text-based parsing."""
        records = []
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            if re.match(r'^(Ministry\s+of|Department\s+of|Department\s+for)\b', line, re.IGNORECASE):
                current_ministry = line
                i += 1
                continue

            if line in ['Aviation & Aviation Infrastructure', 'Coal', 'Electricity Generation', 'Railways',
                        'Transmission & Distribution', 'Real Estate', 'Urban Public Transport', 'Waste & Water',
                        'Water Resources', 'Steel', 'Metals & Mining', 'Construction', 'Shipping',
                        'Inland Waterways', 'Tourism, Hospitality & Wellness', 'Education', 'Telecommunication',
                        'Energy Storage', 'Oil & Gas', 'Healthcare']:
                current_sector = line
                i += 1
                continue

            m_sl = re.match(r'^(\d+)$', line)
            if m_sl:
                sl_no = int(m_sl.group(1))
                i += 1
                proj_lines = []
                while i < len(lines) and not re.search(r'^\d{2}/\d{4}', lines[i].strip()) and not re.match(r'^\d+$', lines[i].strip()):
                    proj_lines.append(lines[i].strip())
                    i += 1
                
                project_cell_text = "\n".join(proj_lines)
                project_name, agency, project_code, legacy_ocms, pmgid = self.parse_project_cell(project_cell_text)
                proj_id = project_code if project_code else f"PROJ_{sl_no}"

                rec = {
                    "sl_no": sl_no,
                    "project_id": proj_id,
                    "project_key": proj_id,
                    "project_name": project_name,
                    "agency": agency,
                    "pmgid": pmgid,
                    "legacy_ocms_code": legacy_ocms,
                    "ministry_department": current_ministry,
                    "sector": current_sector,
                    "state": "",
                    "report_month": report_month,
                    "approval_start": None,
                    "original_target_doc": None,
                    "revised_doc": None,
                    "original_cost_crore": None,
                    "revised_cost_crore": None,
                    "cumulative_expenditure_crore": None,
                    "physical_progress_pct": None,
                    "page": page_num,
                    "source_report": source_report
                }
                records.append(rec)
                continue

            i += 1

        return current_ministry, current_sector, records

    def _parse_dual_doc(self, doc_str: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse original and revised target DoC from cell."""
        lines = [line.strip() for line in doc_str.split('\n') if line.strip()]
        if not lines:
            return None, None
        
        orig_doc = parse_date_mmyyyy(lines[0])
        rev_doc = None
        if len(lines) > 1:
            rev_doc = parse_date_mmyyyy(lines[1])
        return orig_doc, rev_doc

    def _parse_dual_cost(self, cost_str: str) -> Tuple[Optional[float], Optional[float]]:
        """Parse original and revised cost from cell."""
        lines = [line.strip() for line in cost_str.split('\n') if line.strip()]
        if not lines:
            return None, None
        
        orig_cost = clean_number(lines[0])
        rev_cost = None
        if len(lines) > 1:
            rev_cost = clean_number(lines[1])
        return orig_cost, rev_cost
