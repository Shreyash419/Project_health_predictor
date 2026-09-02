"""
Extractor module for discovering PDF reports and locating Table 4.
"""
import os
import re
import glob
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

MONTH_NAMES = {
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12
}


class TableNotFoundError(Exception):
    """Raised when Table 4 cannot be confidently identified in the report."""
    pass


class ReportExtractor:
    """Discovers monthly reports, identifies report month, and isolates Table 4 pages."""

    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = reports_dir

    def discover_reports(self) -> List[str]:
        """Discover all PDF report files in reports_dir and sort them chronologically by report month."""
        if not os.path.exists(self.reports_dir):
            os.makedirs(self.reports_dir, exist_ok=True)
            return []
        
        pdf_files = glob.glob(os.path.join(self.reports_dir, "*.pdf"))
        
        # Sort chronologically by report month
        def get_report_sort_key(fpath: str) -> Tuple[str, str]:
            try:
                doc = fitz.open(fpath)
                m = self.parse_report_month(doc, fpath)
                doc.close()
                if m:
                    return (m, os.path.basename(fpath))
            except Exception:
                pass
            return ("9999-99-99", os.path.basename(fpath))

        pdf_files.sort(key=get_report_sort_key)
        return pdf_files

    def parse_report_month(self, doc: fitz.Document, file_path: str) -> Optional[str]:
        """
        Extract report month in YYYY-MM-01 format.
        Checks filename first, then cover / early pages.
        """
        # Try from filename first
        base_name = os.path.basename(file_path).lower()
        for month_name, month_num in MONTH_NAMES.items():
            pattern = rf'{month_name}[_\s-]*(\d{{4}})'
            match = re.search(pattern, base_name)
            if match:
                year = int(match.group(1))
                return f"{year:04d}-{month_num:02d}-01"

        # Try from first 5 pages of PDF
        num_pages_to_check = min(5, len(doc))
        for page_idx in range(num_pages_to_check):
            text = doc[page_idx].get_text()
            for month_name, month_num in MONTH_NAMES.items():
                pattern = rf'\b{month_name}\s+(\d{{4}})\b'
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    year = int(match.group(1))
                    return f"{year:04d}-{month_num:02d}-01"

        return None

    def find_table4_pages(self, doc: fitz.Document) -> Tuple[int, int]:
        """
        Locate the start and end 0-indexed page numbers for 'All Ongoing Projects' (Table 4 / Table 6).
        Returns (start_page_idx, end_page_idx) inclusive.
        Raises TableNotFoundError if the table cannot be confidently identified.
        """
        start_page_idx = -1
        end_page_idx = -1

        total_pages = len(doc)
        for page_idx in range(total_pages):
            page_text = doc[page_idx].get_text()
            page_text_clean = " ".join(page_text.split())

            # Skip contents / index page
            if re.search(r'\bCONTENTS\b', page_text_clean, re.IGNORECASE) or re.search(r'Appendix\s*:\s*List\s*of\s*Tables', page_text_clean, re.IGNORECASE):
                continue

            # Check for All Ongoing Projects divider / title page or table header
            is_table_title = bool(re.search(r'Table\s*\d+\s*:\s*All\s*Ongoing\s*Projects', page_text_clean, re.IGNORECASE))
            is_table_header = bool(re.search(r'All\s*Ongoing\s*Projects', page_text_clean, re.IGNORECASE) and 
                                    re.search(r'Sl\.?\s*No', page_text_clean, re.IGNORECASE) and 
                                    re.search(r'Project\s*Name', page_text_clean, re.IGNORECASE))

            if is_table_title or is_table_header:
                if start_page_idx == -1:
                    if is_table_header:
                        start_page_idx = page_idx
                    else:
                        start_page_idx = page_idx + 1
                    end_page_idx = start_page_idx
                else:
                    if is_table_header or "All Ongoing Projects" in page_text:
                        end_page_idx = page_idx

        # Check if table was found
        if start_page_idx == -1 or start_page_idx >= total_pages:
            raise TableNotFoundError("Could not find 'All Ongoing Projects' table in document.")

        # Refine end_page_idx: scan from start_page_idx forward until table structure ceases
        actual_end_idx = start_page_idx
        for page_idx in range(start_page_idx, total_pages):
            text = doc[page_idx].get_text()
            text_clean = " ".join(text.split())
            
            # If we hit next table or section or back cover without data
            if re.search(r'Table\s*(?:7|8|9|5)\b', text_clean, re.IGNORECASE) or \
               re.search(r'Appendix\s*:\s*List\s*of\s*Completed', text_clean, re.IGNORECASE):
                break

            # Confirm page has All Ongoing Projects characteristics or project data
            if "All Ongoing Projects" in text_clean or re.search(r'Sl\.?\s*No', text_clean, re.IGNORECASE):
                actual_end_idx = page_idx
            else:
                break

        end_page_idx = max(end_page_idx, actual_end_idx)
        logger.info(f"Located 'All Ongoing Projects' from page {start_page_idx + 1} to {end_page_idx + 1} (Total {end_page_idx - start_page_idx + 1} pages)")
        return start_page_idx, end_page_idx

    def extract_table4_data(self, file_path: str) -> Dict[str, Any]:
        """
        Extract Table 4 content from PDF.
        Returns a dictionary with report metadata and extracted page blocks.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        doc = fitz.open(file_path)
        try:
            report_month = self.parse_report_month(doc, file_path)
            if not report_month:
                logger.warning(f"Could not automatically detect report month for {file_path}, defaulting to today's month.")
                report_month = datetime.today().strftime('%Y-%m-01')

            start_page, end_page = self.find_table4_pages(doc)

            pages_data = []
            for page_num in range(start_page, end_page + 1):
                page = doc[page_num]
                
                # Extract tables directly while doc is active
                table_rows = []
                try:
                    tabs = page.find_tables()
                    if tabs.tables:
                        for t in tabs.tables:
                            for r in t.extract():
                                # Clean leading and trailing None/empty items
                                clean_r = list(r)
                                while clean_r and (clean_r[0] is None or clean_r[0] == ''):
                                    clean_r.pop(0)
                                while clean_r and (clean_r[-1] is None or clean_r[-1] == ''):
                                    clean_r.pop()
                                if clean_r:
                                    table_rows.append(clean_r)
                except Exception as e:
                    logger.debug(f"find_tables error on page {page_num+1}: {e}")

                pages_data.append({
                    "page_number": page_num + 1,
                    "text": page.get_text("text"),
                    "table_rows": table_rows
                })

            return {
                "source_report": os.path.basename(file_path),
                "file_path": file_path,
                "report_month": report_month,
                "start_page": start_page + 1,
                "end_page": end_page + 1,
                "pages_data": pages_data
            }
        finally:
            doc.close()
