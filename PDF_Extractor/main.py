"""
PAIMANA Monthly Report Extraction and Master Data Pipeline Orchestrator.
"""
import os
import sys
import yaml
import logging
import argparse
from typing import List, Dict, Any, Optional

from src.extractor import ReportExtractor, TableNotFoundError
from src.table4_parser import Table4Parser
from src.project_matcher import ProjectMatcher
from src.feature_engineering import FeatureEngineer
from src.validation import DataValidator
from src.master_manager import MasterManager, EXACT_55_COLUMNS
from src.export_csv import export_to_csv


def setup_logger(log_file: str = "logs/pipeline.log") -> logging.Logger:
    """Setup dual console and file logging."""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger = logging.getLogger("paimana_pipeline")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Stream handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger


class PaimanaPipeline:
    """End-to-end extraction and master data pipeline for PAIMANA monthly infrastructure reports."""

    def __init__(self, config_path: str = "config/feature_config.yaml",
                 reports_dir: str = "reports",
                 master_path: str = "master/PAIMANA_Master.xlsx",
                 csv_path: str = "master/PAIMANA_Master.csv",
                 logger: Optional[logging.Logger] = None):
        self.config_path = config_path
        self.reports_dir = reports_dir
        self.master_path = master_path
        self.csv_path = csv_path
        self.logger = logger or logging.getLogger("paimana_pipeline")

        self.config = self._load_config()
        self.extractor = ReportExtractor(reports_dir=self.reports_dir)
        self.parser = Table4Parser(config=self.config)
        self.feature_engineer = FeatureEngineer(config=self.config)
        self.validator = DataValidator(config=self.config)
        self.master_manager = MasterManager(master_path=self.master_path, config_path=self.config_path)

    def _load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}

    def process_report_file(self, file_path: str, allow_reprocessing: bool = False, fresh: bool = False) -> Dict[str, Any]:
        """
        Process a single PAIMANA monthly report PDF file.
        """
        self.logger.info(f"=== Starting Processing: {file_path} ===")
        
        # Step 1: Extract Table 4 only
        try:
            extracted_data = self.extractor.extract_table4_data(file_path)
        except TableNotFoundError as e:
            self.logger.error(f"Failed locating Table 4 in {file_path}: {e}")
            return {"status": "FAILED", "error": str(e), "data_quality_flag": "SOURCE_TABLE_NOT_FOUND"}
        except Exception as e:
            self.logger.error(f"Unexpected error extracting {file_path}: {e}", exc_info=True)
            return {"status": "FAILED", "error": str(e)}

        report_month = extracted_data["report_month"]
        self.logger.info(f"Identified Report Month: {report_month} | Table 4 Pages: {extracted_data['start_page']} to {extracted_data['end_page']}")

        # Step 2: Parse Table 4 rows
        raw_records = self.parser.parse_pages(extracted_data)
        if not raw_records:
            self.logger.warning(f"No project records parsed from Table 4 in {file_path}.")
            return {"status": "EMPTY", "records_count": 0}

        # Step 3: Match projects against existing Master dataset
        existing_master = [] if fresh else self.master_manager.load_existing_records()
        matcher = ProjectMatcher(existing_master_records=existing_master)
        matched_records = matcher.match_and_assign_ids(raw_records)

        # Step 4: Calculate derived features using project history
        all_records_by_project: Dict[str, List[Dict[str, Any]]] = {}
        for r in existing_master:
            pid = str(r.get("project_id", ""))
            if pid:
                all_records_by_project.setdefault(pid, []).append(r)

        processed_new_snapshots = []
        for new_rec in matched_records:
            pid = new_rec["project_id"]
            proj_history = list(all_records_by_project.get(pid, []))
            
            # Filter out identical report_month from history if reprocessing
            proj_history = [h for h in proj_history if str(h.get("report_month")) != str(report_month)]
            proj_history.append(new_rec)
            
            # Calculate features for this project's timeline
            enriched_timeline = self.feature_engineer.calculate_features_for_project(proj_history)
            current_enriched = [row for row in enriched_timeline if str(row.get("report_month")) == str(report_month)][-1]
            processed_new_snapshots.append(current_enriched)

        # Step 5: Validate records & assign data quality flags
        existing_keys = set() if fresh else self.master_manager.get_existing_keys()
        validated_records = self.validator.validate_dataset(processed_new_snapshots, existing_keys=existing_keys)

        # Step 6: Merge & save to Master Excel
        added, skipped, change_logs = self.master_manager.merge_and_save(
            validated_records, allow_reprocessing=allow_reprocessing, fresh=fresh
        )

        self.logger.info(f"Report {file_path} processing finished: {added} new snapshots added, {skipped} duplicate snapshots skipped.")

        return {
            "status": "SUCCESS",
            "file_path": file_path,
            "report_month": report_month,
            "extracted_count": len(raw_records),
            "added_count": added,
            "skipped_count": skipped,
            "change_logs": change_logs
        }

    def run_all(self, allow_reprocessing: bool = False, export_csv_flag: bool = True, fresh: bool = False) -> List[Dict[str, Any]]:
        """
        Scan reports directory and process all discovered reports chronologically.
        """
        reports = self.extractor.discover_reports()
        if not reports:
            self.logger.info(f"No PDF reports found in {self.reports_dir}.")
            return []

        self.logger.info(f"Found {len(reports)} PDF report(s) in {self.reports_dir}: {[os.path.basename(r) for r in reports]}")
        results = []
        for idx, report_file in enumerate(reports):
            # Apply fresh only on the first file if multiple
            is_fresh = fresh and (idx == 0)
            res = self.process_report_file(report_file, allow_reprocessing=allow_reprocessing, fresh=is_fresh)
            results.append(res)

        if export_csv_flag:
            target_excel = self.master_path
            backup_path = self.master_path.replace(".xlsx", "_latest.xlsx")
            if not os.path.exists(target_excel) and os.path.exists(backup_path):
                target_excel = backup_path
            if os.path.exists(target_excel):
                self.logger.info("Exporting Master Excel to CSV...")
                try:
                    export_to_csv(target_excel, self.csv_path)
                except Exception as e:
                    self.logger.warning(f"Could not export CSV from {target_excel}: {e}")

        return results


def main():
    parser = argparse.ArgumentParser(description="PAIMANA Monthly Infrastructure Report Ingestion Pipeline")
    parser.add_argument("--reports-dir", default="reports", help="Directory containing monthly PDF reports")
    parser.add_argument("--report-file", default=None, help="Path to a single specific report PDF to process")
    parser.add_argument("--master-path", default="master/PAIMANA_Master.xlsx", help="Path to Master Excel file")
    parser.add_argument("--csv-path", default="master/PAIMANA_Master.csv", help="Path to Master CSV export file")
    parser.add_argument("--config", default="config/feature_config.yaml", help="Path to configuration YAML")
    parser.add_argument("--allow-reprocessing", action="store_true", help="Allow updating existing project-month snapshots")
    parser.add_argument("--fresh", action="store_true", help="Completely reset/refresh the Master file from scratch")
    parser.add_argument("--no-csv", action="store_true", help="Do not auto-export to CSV after run")
    args = parser.parse_args()

    logger = setup_logger()
    logger.info("Initializing PAIMANA Pipeline...")

    pipeline = PaimanaPipeline(
        config_path=args.config,
        reports_dir=args.reports_dir,
        master_path=args.master_path,
        csv_path=args.csv_path,
        logger=logger
    )

    if args.report_file:
        res = pipeline.process_report_file(args.report_file, allow_reprocessing=args.allow_reprocessing, fresh=args.fresh)
        if not args.no_csv:
            target_excel = args.master_path
            backup_path = args.master_path.replace(".xlsx", "_latest.xlsx")
            if not os.path.exists(target_excel) and os.path.exists(backup_path):
                target_excel = backup_path
            if os.path.exists(target_excel):
                export_to_csv(target_excel, args.csv_path)
    else:
        pipeline.run_all(allow_reprocessing=args.allow_reprocessing, export_csv_flag=not args.no_csv, fresh=args.fresh)


if __name__ == "__main__":
    main()
