"""
CSV Exporter: Converts master/PAIMANA_Master.xlsx to master/PAIMANA_Master.csv,
preserving exact column order, datatypes, and null representations.
"""
import os
import argparse
import logging
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_EXCEL_PATH = "master/PAIMANA_Master.xlsx"
DEFAULT_CSV_PATH = "master/PAIMANA_Master.csv"
SHEET_NAME = "Project_Monthly_Data"


def export_to_csv(excel_path: str = DEFAULT_EXCEL_PATH, csv_path: str = DEFAULT_CSV_PATH) -> str:
    """
    Export the Master Excel worksheet to CSV, guaranteeing rows are arranged in ascending order
    by project_id and report_month.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Master Excel file not found at: {excel_path}")

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    df = pd.read_excel(excel_path, sheet_name=SHEET_NAME, engine="openpyxl")
    
    # Sort ascending by project_id (numeric-aware) and report_month
    if "project_id" in df.columns and "report_month" in df.columns:
        is_num = df["project_id"].astype(str).str.isdigit()
        df_num = df[is_num].copy()
        df_num["_sort_id"] = df_num["project_id"].astype(int)
        df_num["_sort_type"] = 0

        df_str = df[~is_num].copy()
        df_str["_sort_id"] = df_str["project_id"].astype(str)
        df_str["_sort_type"] = 1

        df_sorted = pd.concat([df_num, df_str], ignore_index=True)
        df_sorted = df_sorted.sort_values(by=["_sort_type", "_sort_id", "report_month"], ascending=[True, True, True])
        df_sorted = df_sorted.drop(columns=["_sort_id", "_sort_type"])
        df = df_sorted

    df.to_csv(csv_path, index=False, encoding="utf-8")
    logger.info(f"Successfully exported {len(df)} rows from {excel_path} to {csv_path} in ascending order.")

    # Also sync to paimana_ml/data/input/PAIMANA_Master.csv if directory exists
    ml_input_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "paimana_ml", "data", "input")
    if os.path.exists(ml_input_dir):
        ml_csv_path = os.path.join(ml_input_dir, "PAIMANA_Master.csv")
        if os.path.abspath(csv_path) != os.path.abspath(ml_csv_path):
            df.to_csv(ml_csv_path, index=False, encoding="utf-8")
            logger.info(f"Synced sorted dataset to {ml_csv_path}")

    return csv_path


def main():
    parser = argparse.ArgumentParser(description="Export PAIMANA Master Excel to CSV for ML data processing.")
    parser.add_argument("--excel", default=DEFAULT_EXCEL_PATH, help="Path to input Master Excel file")
    parser.add_argument("--csv", default=DEFAULT_CSV_PATH, help="Path to output CSV file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        out_path = export_to_csv(args.excel, args.csv)
        print(f"Exported Master CSV successfully to: {out_path}")
    except Exception as e:
        print(f"Error during CSV export: {e}")
        exit(1)


if __name__ == "__main__":
    main()
