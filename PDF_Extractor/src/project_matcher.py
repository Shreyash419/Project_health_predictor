"""
Project Matcher: Identifies projects across monthly reports using Project Code and maintains project identity.
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def normalize_string(s: Optional[str]) -> str:
    """Normalize text by removing punctuation, extra whitespace, and converting to lowercase."""
    if not s:
        return ""
    cleaned = re.sub(r'[^a-zA-Z0-9]', ' ', str(s))
    return " ".join(cleaned.lower().split())


class ProjectMatcher:
    """
    Maintains project identity registry and matches newly extracted records against existing projects.
    """

    def __init__(self, existing_master_records: Optional[List[Dict[str, Any]]] = None):
        self.code_to_id: Dict[str, str] = {}
        self.key_to_id: Dict[str, str] = {}
        self.id_to_project_info: Dict[str, Dict[str, Any]] = {}
        self.max_id_num = 0

        if existing_master_records:
            self.build_index_from_existing(existing_master_records)

    def build_index_from_existing(self, master_records: List[Dict[str, Any]]):
        """Index existing master records to ensure stable project_id assignment."""
        for rec in master_records:
            proj_id = rec.get("project_id")
            if not proj_id:
                continue

            proj_id_str = str(proj_id).strip()
            self.code_to_id[proj_id_str] = proj_id_str
            self.key_to_id[proj_id_str] = proj_id_str

            if proj_id_str not in self.id_to_project_info:
                self.id_to_project_info[proj_id_str] = {
                    "project_id": proj_id_str,
                    "project_name": rec.get("project_name"),
                    "agency": rec.get("agency"),
                    "ministry_department": rec.get("ministry_department"),
                    "sector": rec.get("sector"),
                    "pmgid": rec.get("pmgid"),
                    "legacy_ocms_code": rec.get("legacy_ocms_code")
                }

    def _generate_new_id(self) -> str:
        """Generate a sequential project ID fallback if project code is missing."""
        self.max_id_num += 1
        return f"P{self.max_id_num:05d}"

    def match_and_assign_ids(self, raw_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Assign stable project_id (Project Code) and project_key to each raw record.
        Rules:
        - project_id = Project Code
        - project_key = project_id
        - legacy_ocms_code and pmgid remain independent and are never cross-copied.
        """
        matched_records = []
        new_projects_count = 0
        existing_projects_count = 0

        for rec in raw_records:
            raw_proj_id = rec.get("project_id")
            if raw_proj_id and str(raw_proj_id).strip():
                proj_id = str(raw_proj_id).strip()
            else:
                proj_id = self._generate_new_id()

            # Rule: project_key MUST be exactly equal to project_id
            project_key = proj_id

            if proj_id in self.id_to_project_info:
                existing_projects_count += 1
            else:
                new_projects_count += 1
                self.code_to_id[proj_id] = proj_id
                self.key_to_id[project_key] = proj_id
                self.id_to_project_info[proj_id] = {
                    "project_id": proj_id,
                    "project_name": rec.get("project_name"),
                    "agency": rec.get("agency"),
                    "ministry_department": rec.get("ministry_department"),
                    "sector": rec.get("sector"),
                    "pmgid": rec.get("pmgid"),
                    "legacy_ocms_code": rec.get("legacy_ocms_code")
                }

            record_copy = dict(rec)
            record_copy["project_id"] = proj_id
            record_copy["project_key"] = project_key
            matched_records.append(record_copy)

        logger.info(f"Project matching complete: {existing_projects_count} matched existing, {new_projects_count} new projects registered.")
        return matched_records
