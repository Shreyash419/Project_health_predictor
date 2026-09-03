"""
End-to-end Pipeline and Specification Verification Tests (Test Cases 1 through 12 + Identifier Mapping Tests).
"""
import os
import shutil
import pytest
import pandas as pd
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from main import PaimanaPipeline
from src.table4_parser import Table4Parser
from src.master_manager import MasterManager, EXACT_55_COLUMNS
from src.export_csv import export_to_csv
from src.validation import DataValidator


def generate_sample_paimana_pdf(pdf_path: str, month_str: str, project_list: list, include_other_tables: bool = True):
    """
    Generate a realistic multi-page PAIMANA PDF containing Table 1, Table 2, Table 3, and multi-page Table 4.
    """
    if os.path.dirname(pdf_path):
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    doc = SimpleDocTemplate(pdf_path, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    story = []

    # Title Page
    story.append(Paragraph("477th Flash Report on Central Sector Infrastructure Projects", styles['Title']))
    story.append(Paragraph(f"Report Month: {month_str}", styles['Heading2']))
    story.append(PageBreak())

    if include_other_tables:
        # Table 1: Ministry-wise Ongoing Projects (SHOULD BE IGNORED)
        story.append(Paragraph("Table 1: Ministry-wise Ongoing Projects", styles['Heading1']))
        t1_data = [
            ["Sl.No", "Allocated To", "Sector", "Project Count", "Original Cost", "Cumulative Expenditure"],
            ["1", "Ministry of Civil Aviation", "Aviation", "27", "23265.01", "5883.97"],
            ["2", "Ministry of Coal", "Coal", "118", "169952.27", "52990.5"]
        ]
        story.append(Table(t1_data, colWidths=[40, 150, 100, 80, 100, 100]))
        story.append(PageBreak())

        # Table 2: State-wise Ongoing Projects (SHOULD BE IGNORED)
        story.append(Paragraph("Table 2: State-wise Ongoing Projects", styles['Heading1']))
        t2_data = [
            ["Sl.No", "STATE NAME", "Allocated To", "Sector", "Project Count", "Cumulative Expenditure"],
            ["1", "Andhra Pradesh", "Ministry of Civil Aviation", "Aviation", "4", "696.24"]
        ]
        story.append(Table(t2_data, colWidths=[40, 120, 150, 100, 80, 100]))
        story.append(PageBreak())

        # Table 3: Ongoing Projects of North Eastern Region (SHOULD BE IGNORED)
        story.append(Paragraph("Table 3: Ongoing Projects North Eastern Region", styles['Heading1']))
        t3_data = [
            ["Sl.No", "Project Name (Agency) (Project Code)", "State", "Date of Approval", "Physical Progress (%)"],
            ["1", "Guwahati Airport Construction\n(AAI)\n(706724)", "Assam", "03/2018", "94.1"]
        ]
        story.append(Table(t3_data, colWidths=[40, 250, 100, 100, 100]))
        story.append(PageBreak())

    # Divider Page for Table 4
    story.append(Paragraph("Table 4: All Ongoing Projects", styles['Title']))
    story.append(PageBreak())

    # Table 4 Pages
    header = [
        "Sl.No",
        "Project Name (Agency) (Project Code)",
        "State",
        "Date of\nApproval\nMM/YYYY",
        "Orignal/Target DoC\n(Revised DoC)\nMM/YYYY",
        "Orignal Cost\nRevised Cost\nin Rs. Crore",
        "Cumulative\nExpenditure\nin Rs. Crore",
        "Physical Progress\n(%)"
    ]

    col_widths = [40, 220, 90, 70, 85, 85, 80, 60]

    chunk_size = 3
    for i in range(0, len(project_list), chunk_size):
        chunk = project_list[i:i + chunk_size]
        page_table_data = [header]
        
        # Add Ministry banner
        page_table_data.append(["Ministry of Railways", "", "", "", "", "", "", ""])
        # Add Sector banner
        page_table_data.append(["Railways", "", "", "", "", "", "", ""])

        for proj in chunk:
            p_cell = f"{proj['name']}\n({proj['agency']})\n({proj['code']})"
            if proj.get("ocms") or proj.get("pmgid"):
                ocms_str = proj.get("ocms", "-") or "-"
                pmgid_str = proj.get("pmgid", "-") or "-"
                p_cell += f"\n({ocms_str}) ({pmgid_str})"
                
            doc_cell = f"{proj['orig_doc']}\n({proj['rev_doc']})"
            cost_cell = f"{proj['orig_cost']}\n({proj['rev_cost']})"
            page_table_data.append([
                str(proj['sl_no']),
                p_cell,
                proj['state'],
                proj['approval'],
                doc_cell,
                cost_cell,
                str(proj['expenditure']),
                str(proj['progress'])
            ])

        story.append(Paragraph("All Ongoing Projects " + month_str, styles['Heading2']))
        t4 = Table(page_table_data, colWidths=col_widths)
        t4.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.navy),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        story.append(t4)
        if i + chunk_size < len(project_list):
            story.append(PageBreak())

    doc.build(story)


@pytest.fixture
def test_env(tmp_path):
    """Setup clean temporary workspace."""
    reports_dir = str(tmp_path / "reports")
    master_path = str(tmp_path / "master" / "PAIMANA_Master.xlsx")
    csv_path = str(tmp_path / "master" / "PAIMANA_Master.csv")
    config_path = "config/feature_config.yaml"
    
    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(os.path.dirname(master_path), exist_ok=True)

    pipeline = PaimanaPipeline(
        config_path=config_path,
        reports_dir=reports_dir,
        master_path=master_path,
        csv_path=csv_path
    )
    return {
        "pipeline": pipeline,
        "reports_dir": reports_dir,
        "master_path": master_path,
        "csv_path": csv_path,
        "tmp_path": tmp_path
    }


def test_schema_columns(test_env):
    """Verify Master Excel contains EXACTLY 55 columns in the exact specified sequence."""
    pipeline = test_env["pipeline"]
    manager = pipeline.master_manager
    assert len(manager.columns) == 55
    assert manager.columns == EXACT_55_COLUMNS


def test_identifier_separation_required_cases():
    """Verify the 4 required test cases and parenthesized name case."""
    parser = Table4Parser()

    # TEST 1
    c1 = "C2/C3 Vijaypur Pata Pipeline\n(Ministry of Petroleum & Natural Gas)\n(617830)\n(-) (10000)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c1)
    assert name == "C2/C3 Vijaypur Pata Pipeline"
    assert ag == "Ministry of Petroleum & Natural Gas"
    assert code == "617830"
    assert ocms is None
    assert pmg == "10000"

    # TEST 2
    c2 = "Some Project Name\n(Ministry of XYZ)\n(709774)\n(N16000437) (-)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c2)
    assert name == "Some Project Name"
    assert ag == "Ministry of XYZ"
    assert code == "709774"
    assert ocms == "N16000437"
    assert pmg is None

    # TEST 3
    c3 = "Some Project Name\n(Ministry of XYZ)\n(709774)\n(N16000437) (12345)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c3)
    assert name == "Some Project Name"
    assert ag == "Ministry of XYZ"
    assert code == "709774"
    assert ocms == "N16000437"
    assert pmg == "12345"

    # TEST 4
    c4 = "Some Project Name\n(Ministry of XYZ)\n(709774)\n(-) (-)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c4)
    assert name == "Some Project Name"
    assert ag == "Ministry of XYZ"
    assert code == "709774"
    assert ocms is None
    assert pmg is None

    # Preserving legitimate parentheses in project_name
    c5 = "Development of Package (A) for Highway\n(Ministry of XYZ)\n(612786)\n(-) (10000)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c5)
    assert name == "Development of Package (A) for Highway"
    assert code == "612786"
    assert pmg == "10000"

    # Single-line inline (Agency) (Project Code)
    c6 = "Construction of new 4 lane major bridge on Sabarmati River (MoRTH) (617926)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c6)
    assert name == "Construction of new 4 lane major bridge on Sabarmati River"
    assert ag == "MoRTH"
    assert code == "617926"

    # Nested parentheses in Agency name
    c7 = "DHULE [BORVIHIR] - NARDANA NEW LINE [50.60 KMS] (Central Railway (CR) - II)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c7)
    assert name == "DHULE [BORVIHIR] - NARDANA NEW LINE [50.60 KMS]"
    assert ag == "Central Railway (CR) - II"

    # Agency with square brackets and project code
    c8 = "4 Laning with PS of Pathrapalli-Katghora (National Highways Authority of India [NHAI]) (619167)"
    name, ag, code, ocms, pmg = parser.parse_project_cell(c8)
    assert name == "4 Laning with PS of Pathrapalli-Katghora"
    assert ag == "National Highways Authority of India [NHAI]"
    assert code == "619167"


def test_single_report_and_table4_only(test_env):
    """
    TEST 1, TEST 9, TEST 10, TEST 12:
    - Single monthly report ingestion.
    - Multi-page Table 4 extraction.
    - Repeated headers ignored.
    - Only Table 4 records extracted (ignoring Table 1, 2, 3).
    """
    reports_dir = test_env["reports_dir"]
    pdf1 = os.path.join(reports_dir, "PAIMANA_July_2025.pdf")

    projects = [
        {"sl_no": 1, "name": "Project Alpha", "agency": "AAI", "code": "600001", "ocms": None, "pmgid": "10000", "state": "Delhi", "approval": "01/2023", "orig_doc": "01/2026", "rev_doc": "06/2026", "orig_cost": "500", "rev_cost": "550", "expenditure": "200", "progress": "40"},
        {"sl_no": 2, "name": "Project Beta", "agency": "NTPC", "code": "600002", "ocms": "N06000100", "pmgid": None, "state": "Gujarat", "approval": "03/2022", "orig_doc": "12/2025", "rev_doc": "-", "orig_cost": "1000", "rev_cost": "1000", "expenditure": "500", "progress": "50"},
        {"sl_no": 3, "name": "Project Gamma", "agency": "NHPC", "code": "600003", "ocms": "N06000200", "pmgid": "12345", "state": "Assam", "approval": "05/2024", "orig_doc": "05/2028", "rev_doc": "-", "orig_cost": "800", "rev_cost": "800", "expenditure": "50", "progress": "10"},
        {"sl_no": 4, "name": "Project Delta", "agency": "IRCON", "code": "600004", "ocms": None, "pmgid": None, "state": "Bihar", "approval": "06/2021", "orig_doc": "06/2025", "rev_doc": "12/2025", "orig_cost": "300", "rev_cost": "350", "expenditure": "280", "progress": "85"},
    ]

    generate_sample_paimana_pdf(pdf1, "JULY 2025", projects, include_other_tables=True)

    pipeline = test_env["pipeline"]
    results = pipeline.run_all()

    assert len(results) == 1
    assert results[0]["status"] == "SUCCESS"
    assert results[0]["added_count"] == 4

    # Verify Master Excel
    df = pd.read_excel(test_env["master_path"], sheet_name="Project_Monthly_Data")
    assert len(df) == 4
    assert list(df.columns) == EXACT_55_COLUMNS
    assert str(df["project_id"].iloc[0]) == "600001"
    assert str(df["project_key"].iloc[0]) == "600001"
    assert int(float(df["pmgid"].iloc[0])) == 10000
    assert pd.isna(df["legacy_ocms_code"].iloc[0])


def test_multi_month_and_project_matching(test_env):
    """
    Multi-month accumulation with Project Code as project_id.
    """
    reports_dir = test_env["reports_dir"]
    pdf1 = os.path.join(reports_dir, "PAIMANA_July_2025.pdf")
    pdf2 = os.path.join(reports_dir, "PAIMANA_August_2025.pdf")

    # Month 1 (July 2025)
    july_projects = [
        {"sl_no": 1, "name": "Project Alpha", "agency": "AAI", "code": "600001", "state": "Delhi", "approval": "01/2023", "orig_doc": "01/2026", "rev_doc": "06/2026", "orig_cost": "500", "rev_cost": "550", "expenditure": "200", "progress": "40"},
        {"sl_no": 2, "name": "Project Beta", "agency": "NTPC", "code": "600002", "state": "Gujarat", "approval": "03/2022", "orig_doc": "12/2025", "rev_doc": "-", "orig_cost": "1000", "rev_cost": "1000", "expenditure": "500", "progress": "50"},
        {"sl_no": 3, "name": "Project Omega (Ending)", "agency": "NHPC", "code": "600003", "state": "Assam", "approval": "01/2020", "orig_doc": "07/2025", "rev_doc": "07/2025", "orig_cost": "800", "rev_cost": "800", "expenditure": "800", "progress": "100"},
    ]
    generate_sample_paimana_pdf(pdf1, "JULY 2025", july_projects)

    # Month 2 (August 2025):
    august_projects = [
        {"sl_no": 1, "name": "Project Alpha (Updated Title)", "agency": "AAI", "code": "600001", "state": "Delhi", "approval": "01/2023", "orig_doc": "01/2026", "rev_doc": "09/2026", "orig_cost": "500", "rev_cost": "550", "expenditure": "230", "progress": "45"},
        {"sl_no": 2, "name": "Project Beta", "agency": "NTPC", "code": "600002", "state": "Gujarat", "approval": "03/2022", "orig_doc": "12/2025", "rev_doc": "-", "orig_cost": "1000", "rev_cost": "1000", "expenditure": "560", "progress": "55"},
        {"sl_no": 3, "name": "Project Epsilon (New in August)", "agency": "IRCON", "code": "600005", "state": "Kerala", "approval": "08/2024", "orig_doc": "08/2027", "rev_doc": "-", "orig_cost": "400", "rev_cost": "400", "expenditure": "20", "progress": "5"},
    ]
    generate_sample_paimana_pdf(pdf2, "AUGUST 2025", august_projects)

    pipeline = test_env["pipeline"]
    results = pipeline.run_all()

    assert len(results) == 2
    assert results[0]["added_count"] == 3
    assert results[1]["added_count"] == 3

    df = pd.read_excel(test_env["master_path"], sheet_name="Project_Monthly_Data")
    assert len(df) == 6

    # Verify project_id is 600001
    alpha_rows = df[df["project_id"].astype(str) == "600001"].sort_values("report_month")
    assert len(alpha_rows) == 2
    assert str(alpha_rows["project_id"].iloc[0]) == str(alpha_rows["project_id"].iloc[1]) == "600001"
    assert str(alpha_rows["project_key"].iloc[0]) == str(alpha_rows["project_key"].iloc[1]) == "600001"
    assert alpha_rows["physical_progress_delta_1m"].iloc[1] == 5.0


def test_validation_flags_and_missing_values():
    """Verify validation rules and IDENTIFIER_EXTRACTION_ERROR flag."""
    validator = DataValidator()
    
    # Valid record
    valid_rec = {
        "project_id": "617830",
        "project_key": "617830",
        "project_name": "C2/C3 Vijaypur Pata Pipeline",
        "report_month": "2025-07-01",
        "physical_progress_pct": 50.0,
        "original_cost_crore": 100.0,
        "revised_cost_crore": 120.0,
        "pmgid": "10000",
        "legacy_ocms_code": None
    }
    is_valid, flag = validator.validate_record(valid_rec)
    assert is_valid is True
    assert flag == "OK"

    # Mismatched project_key vs project_id
    bad_key = dict(valid_rec, project_key="PMGID_10000")
    is_valid, flag = validator.validate_record(bad_key)
    assert is_valid is False
    assert flag == "IDENTIFIER_EXTRACTION_ERROR"

    # Suffix in project_name
    bad_name = dict(valid_rec, project_name="C2/C3 Vijaypur Pata Pipeline (617830)")
    is_valid, flag = validator.validate_record(bad_name)
    assert is_valid is False
    assert flag == "IDENTIFIER_EXTRACTION_ERROR"


def test_csv_export(test_env):
    """Verify CSV export maintains all 55 columns and rows."""
    pipeline = test_env["pipeline"]
    pdf1 = os.path.join(test_env["reports_dir"], "PAIMANA_July_2025.pdf")
    generate_sample_paimana_pdf(pdf1, "JULY 2025", [
        {"sl_no": 1, "name": "Project Alpha", "agency": "AAI", "code": "600001", "state": "Delhi", "approval": "01/2023", "orig_doc": "01/2026", "rev_doc": "-", "orig_cost": "500", "rev_cost": "500", "expenditure": "200", "progress": "40"}
    ])
    pipeline.run_all()

    csv_path = test_env["csv_path"]
    assert os.path.exists(csv_path)

    df_csv = pd.read_csv(csv_path)
    assert len(df_csv) == 1
    assert list(df_csv.columns) == EXACT_55_COLUMNS
    assert str(df_csv["project_id"].iloc[0]) == "600001"
    assert str(df_csv["project_key"].iloc[0]) == "600001"
