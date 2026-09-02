"""
Tests for Derived Features and Mathematical / Temporal Calculations.
"""
import pytest
from src.feature_engineering import FeatureEngineer, months_between, compute_linear_slope


def test_months_between():
    from datetime import date
    d1 = date(2025, 1, 1)
    d2 = date(2025, 7, 1)
    assert months_between(d1, d2) == 6
    assert months_between(d2, d1) == -6
    assert months_between(d1, d1) == 0


def test_linear_slope():
    y = [10.0, 20.0, 30.0]
    # slope should be 10.0
    slope = compute_linear_slope(y)
    assert slope == 10.0

    y_flat = [50.0, 50.0, 50.0]
    assert compute_linear_slope(y_flat) == 0.0


def test_derived_features_single_snapshot():
    engineer = FeatureEngineer()
    row = {
        "project_id": "P00001",
        "project_key": "PROJ_TEST",
        "project_name": "Test Port Project",
        "agency": "Port Trust",
        "ministry_department": "Ministry of Ports",
        "sector": "Shipping",
        "state": "Maharashtra",
        "report_month": "2025-07-01",
        "approval_start": "2024-01-01",
        "original_target_doc": "2026-01-01",
        "revised_doc": "2026-07-01",
        "original_cost_crore": 1000.0,
        "revised_cost_crore": 1200.0,
        "cumulative_expenditure_crore": 600.0,
        "physical_progress_pct": 50.0
    }

    timeline = engineer.calculate_features_for_project([row])
    assert len(timeline) == 1
    res = timeline[0]

    # Date metrics
    assert res["project_age_months"] == 18  # 2024-01 to 2025-07
    assert res["original_duration_months"] == 24  # 2024-01 to 2026-01
    assert res["planned_remaining_months"] == 6  # 2025-07 to 2026-01
    assert res["revised_remaining_months"] == 12  # 2025-07 to 2026-07
    assert res["schedule_extension_months"] == 6  # 2026-01 to 2026-07
    assert res["extension_rate_pct"] == 25.0  # 6 / 24 * 100
    assert res["days_to_original_target"] == 184  # 2025-07-01 to 2026-01-01
    assert res["schedule_status"] == "EXTENDED"
    assert res["overdue_days"] == 0

    # Financial metrics
    assert res["cost_escalation_crore"] == 200.0
    assert res["cost_escalation_ratio"] == 1.2
    assert res["remaining_budget_crore"] == 600.0  # 1200 - 600
    assert res["cost_overrun_pct"] == 20.0  # (1200 - 1000) / 1000 * 100
    assert res["expenditure_ratio_pct"] == 50.0  # 600 / 1200 * 100

    # Progress metrics
    assert res["remaining_work_pct"] == 50.0
    assert res["physical_financial_gap_pct"] == 0.0  # 50 - 50
    assert res["physical_to_expenditure_ratio"] == 1.0  # 50 / 50
    assert res["progress_expenditure_mismatch_flag"] == 0
    assert res["high_expenditure_low_progress_flag"] == 0

    # Without history, delta/lag/slope metrics are None
    assert res["physical_progress_delta_1m"] is None
    assert res["progress_velocity_3m"] is None
    assert res["progress_trend_slope"] is None


def test_derived_features_multi_month_timeline():
    engineer = FeatureEngineer()
    # 4 consecutive months: July, August, September, October 2025
    timeline_input = [
        {
            "project_id": "P00001",
            "report_month": "2025-07-01",
            "approval_start": "2024-01-01",
            "original_target_doc": "2026-01-01",
            "revised_doc": "2026-01-01",
            "original_cost_crore": 1000.0,
            "revised_cost_crore": 1000.0,
            "cumulative_expenditure_crore": 200.0,
            "physical_progress_pct": 20.0
        },
        {
            "project_id": "P00001",
            "report_month": "2025-08-01",
            "approval_start": "2024-01-01",
            "original_target_doc": "2026-01-01",
            "revised_doc": "2026-01-01",
            "original_cost_crore": 1000.0,
            "revised_cost_crore": 1000.0,
            "cumulative_expenditure_crore": 250.0,
            "physical_progress_pct": 25.0
        },
        {
            "project_id": "P00001",
            "report_month": "2025-09-01",
            "approval_start": "2024-01-01",
            "original_target_doc": "2026-01-01",
            "revised_doc": "2026-01-01",
            "original_cost_crore": 1000.0,
            "revised_cost_crore": 1000.0,
            "cumulative_expenditure_crore": 300.0,
            "physical_progress_pct": 30.0
        },
        {
            "project_id": "P00001",
            "report_month": "2025-10-01",
            "approval_start": "2024-01-01",
            "original_target_doc": "2026-01-01",
            "revised_doc": "2026-04-01",
            "original_cost_crore": 1000.0,
            "revised_cost_crore": 1100.0,
            "cumulative_expenditure_crore": 400.0,
            "physical_progress_pct": 35.0
        }
    ]

    enriched = engineer.calculate_features_for_project(timeline_input)
    assert len(enriched) == 4

    # Month 1 (July)
    assert enriched[0]["physical_progress_delta_1m"] is None
    assert enriched[0]["expenditure_velocity_crore_month"] is None

    # Month 2 (August)
    assert enriched[1]["physical_progress_delta_1m"] == 5.0
    assert enriched[1]["expenditure_velocity_crore_month"] == 50.0  # 250 - 200

    # Month 4 (October)
    assert enriched[3]["physical_progress_delta_1m"] == 5.0
    assert enriched[3]["physical_progress_delta_3m"] == 15.0  # 35 - 20 (July is 3m prior)
    assert enriched[3]["progress_velocity_3m"] == 5.0  # (35 - 20) / 3
    assert enriched[3]["progress_trend_slope"] == 5.0  # 5% per month slope
    assert enriched[3]["cost_overrun_delta_1m"] == 10.0  # 10% - 0%
    assert enriched[3]["schedule_extension_delta_1m"] == 3  # 3 months extension added in Oct
