"""
Validation Module: Validates records, verifies business rules, and assigns data_quality_flag.
"""
import re
import logging
from typing import Dict, Any, List, Set, Tuple, Optional

logger = logging.getLogger(__name__)

VALID_FLAGS = [
    "OK",
    "IDENTIFIER_EXTRACTION_ERROR",
    "MISSING_REQUIRED_FIELD",
    "INVALID_DATE",
    "INVALID_PERCENTAGE",
    "DUPLICATE_RECORD",
    "POSSIBLE_OCR_ERROR",
    "INSUFFICIENT_HISTORY",
    "SOURCE_TABLE_NOT_FOUND"
]


class DataValidator:
    """Validates project snapshot records and assigns appropriate data quality flags."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def validate_record(self, record: Dict[str, Any], seen_keys: Optional[Set[Tuple[str, str]]] = None) -> Tuple[bool, str]:
        """
        Validate an individual record against all schema and identifier mapping rules.
        Returns (is_valid, data_quality_flag).
        """
        proj_id = record.get("project_id")
        proj_key = record.get("project_key")
        report_month = record.get("report_month")
        proj_name = str(record.get("project_name", "")).strip()
        pmgid = record.get("pmgid")
        legacy_ocms = record.get("legacy_ocms_code")

        # 1. Check required fields
        if not proj_id or not str(proj_id).strip():
            return False, "MISSING_REQUIRED_FIELD"
        if not report_month or not str(report_month).strip():
            return False, "MISSING_REQUIRED_FIELD"

        # 2. Check duplicates
        if seen_keys is not None:
            key = (str(proj_id), str(report_month))
            if key in seen_keys:
                return False, "DUPLICATE_RECORD"

        # 3. Identifier Extraction Rules (Section 12 of spec)
        # Rule 1: project_key == project_id
        if str(proj_key) != str(proj_id):
            return False, "IDENTIFIER_EXTRACTION_ERROR"

        # Rule 2: project_name must NOT contain project_id as an identifier suffix e.g. '(617830)'
        if proj_id and re.search(rf'\({re.escape(str(proj_id))}\)\s*$', proj_name):
            return False, "IDENTIFIER_EXTRACTION_ERROR"

        # Rule 3: project_name must NOT contain PMGID as an identifier suffix
        if pmgid and re.search(rf'\({re.escape(str(pmgid))}\)\s*$', proj_name):
            return False, "IDENTIFIER_EXTRACTION_ERROR"

        # Rule 4: project_name must NOT contain Legacy OCMS Code as an identifier suffix
        if legacy_ocms and re.search(rf'\({re.escape(str(legacy_ocms))}\)\s*$', proj_name):
            return False, "IDENTIFIER_EXTRACTION_ERROR"

        # Rule 5 & 6: Missing identifiers must remain NULL (not '-' or '(-)')
        if pmgid is not None and str(pmgid).strip() in ['-', '(-)', '—', '–', 'none', 'null']:
            return False, "IDENTIFIER_EXTRACTION_ERROR"
        if legacy_ocms is not None and str(legacy_ocms).strip() in ['-', '(-)', '—', '–', 'none', 'null']:
            return False, "IDENTIFIER_EXTRACTION_ERROR"

        # 4. Check dates format
        for date_field in ["report_month", "approval_start", "original_target_doc", "revised_doc"]:
            val = record.get(date_field)
            if val is not None and str(val).strip():
                val_str = str(val).strip()
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', val_str):
                    return False, "INVALID_DATE"

        # 5. Check percentage ranges
        phys_prog = record.get("physical_progress_pct")
        if phys_prog is not None:
            try:
                prog_val = float(phys_prog)
                if prog_val < 0.0 or prog_val > 100.0:
                    return False, "INVALID_PERCENTAGE"
            except (ValueError, TypeError):
                return False, "POSSIBLE_OCR_ERROR"

        exp_ratio = record.get("expenditure_ratio_pct")
        if exp_ratio is not None:
            try:
                exp_val = float(exp_ratio)
                if exp_val < 0.0:
                    return False, "INVALID_PERCENTAGE"
            except (ValueError, TypeError):
                return False, "POSSIBLE_OCR_ERROR"

        # 6. Check costs
        for cost_field in ["original_cost_crore", "revised_cost_crore", "cumulative_expenditure_crore"]:
            cost_val = record.get(cost_field)
            if cost_val is not None:
                try:
                    c = float(cost_val)
                    if c < 0.0:
                        return False, "POSSIBLE_OCR_ERROR"
                except (ValueError, TypeError):
                    return False, "POSSIBLE_OCR_ERROR"

        return True, "OK"

    def validate_dataset(self, records: List[Dict[str, Any]], existing_keys: Optional[Set[Tuple[str, str]]] = None) -> List[Dict[str, Any]]:
        """
        Validate a batch of records, attaching or updating the data_quality_flag.
        """
        seen_in_batch: Set[Tuple[str, str]] = set()
        if existing_keys:
            seen_in_batch.update(existing_keys)

        validated_records = []
        for rec in records:
            rec_copy = dict(rec)
            proj_id = str(rec_copy.get("project_id", ""))
            report_month = str(rec_copy.get("report_month", ""))
            
            is_valid, flag = self.validate_record(rec_copy, seen_in_batch)
            rec_copy["data_quality_flag"] = flag

            if proj_id and report_month and flag != "DUPLICATE_RECORD":
                seen_in_batch.add((proj_id, report_month))

            validated_records.append(rec_copy)

        return validated_records
