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
    Export the Master Excel worksheet to CSV.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Master Excel file not found at: {excel_path}")

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    df = pd.read_excel(excel_path, sheet_name=SHEET_NAME, engine="openpyxl")
    df.to_csv(csv_path, index=False, encoding="utf-8")
    logger.info(f"Successfully exported {len(df)} rows from {excel_path} to {csv_path}.")
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
