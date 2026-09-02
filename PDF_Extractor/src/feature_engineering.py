import re
import math
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_date(d: Any) -> Optional[date]:
    """Parse date string, datetime, date, or pandas Timestamp into a standard datetime.date object."""
    if d is None:
        return None
    if hasattr(d, "date") and callable(getattr(d, "date")):
        return d.date()
    if isinstance(d, date):
        return d
    try:
        s = str(d).strip()
        if not s or s.lower() in ['nan', 'none', 'nat', '-']:
            return None
        # Handle YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
        m = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        # Handle MM/YYYY
        m_my = re.search(r'(\d{1,2})[/\-](\d{4})', s)
        if m_my:
            return date(int(m_my.group(2)), int(m_my.group(1)), 1)
    except Exception:
        pass
    return None


def months_between(d1: Optional[date], d2: Optional[date]) -> Optional[int]:
    """Calculate the number of full calendar months between d1 and d2 (d2 - d1)."""
    if d1 is None or d2 is None:
        return None
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def compute_linear_slope(y_vals: List[float], x_vals: Optional[List[float]] = None) -> Optional[float]:
    """
    Compute ordinary least squares linear slope.
    y_vals: list of float values
    x_vals: optional list of x coordinates (defaults to 0, 1, 2, ...)
    """
    if len(y_vals) < 2:
        return None
    if x_vals is None:
        x_vals = list(range(len(y_vals)))

    n = len(y_vals)
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
    denominator = sum((x - x_mean) ** 2 for x in x_vals)

    if abs(denominator) < 1e-9:
        return 0.0

    return round(numerator / denominator, 4)


class FeatureEngineer:
    """Calculates all 33 derived features for project snapshots."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        thresholds = self.config.get("thresholds", {})
        self.gap_threshold = thresholds.get("physical_financial_gap_threshold_pct", 15.0)
        self.high_exp_threshold = thresholds.get("high_expenditure_threshold_pct", 70.0)
        self.low_prog_threshold = thresholds.get("low_progress_threshold_pct", 30.0)
        self.stagnation_threshold = thresholds.get("stagnation_progress_threshold_pct", 0.5)
        self.cost_overrun_warning = thresholds.get("cost_overrun_warning_pct", 10.0)
        
        trend_cfg = self.config.get("trend_analysis", {})
        self.min_slope_obs = trend_cfg.get("min_observations_for_slope", 3)

    def calculate_features_for_project(self, historical_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a list of chronological historical snapshots for a SINGLE project.
        historical_rows must be sorted by report_month ascending.
        Calculates features strictly without forward-looking data leakage.
        """
        # Sort chronologically by report_month
        sorted_rows = sorted(historical_rows, key=lambda r: str(r.get("report_month", "")))

        enriched_rows = []
        for idx in range(len(sorted_rows)):
            current = dict(sorted_rows[idx])
            # Past snapshots up to and including current snapshot (NO DATA LEAKAGE)
            # Using already enriched previous rows allows delta/slope of derived metrics
            past_window = enriched_rows + [current]

            enriched = self._enrich_single_snapshot(current, past_window)
            enriched_rows.append(enriched)

        return enriched_rows

    def _enrich_single_snapshot(self, current: Dict[str, Any], past_window: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute all derived fields for the current snapshot using its available history."""
        row = dict(current)

        # Parse primary dates
        report_dt = parse_date(row.get("report_month"))
        approval_dt = parse_date(row.get("approval_start"))
        orig_doc_dt = parse_date(row.get("original_target_doc"))
        rev_doc_dt = parse_date(row.get("revised_doc"))
        target_doc_dt = rev_doc_dt if rev_doc_dt else orig_doc_dt

        # Parse costs & progress
        orig_cost = row.get("original_cost_crore")
        rev_cost = row.get("revised_cost_crore")
        if rev_cost is None and orig_cost is not None:
            rev_cost = orig_cost
        row["revised_cost_crore"] = rev_cost

        cum_exp = row.get("cumulative_expenditure_crore")
        phys_prog = row.get("physical_progress_pct")

        # -------------------------------------------------------------
        # 1. DATE DERIVED FEATURES
        # -------------------------------------------------------------
        # project_age_months: months_between(approval_start, report_month)
        project_age = months_between(approval_dt, report_dt)
        row["project_age_months"] = project_age

        # original_duration_months: months_between(approval_start, original_target_doc)
        orig_dur = months_between(approval_dt, orig_doc_dt)
        row["original_duration_months"] = orig_dur

        # planned_remaining_months: months_between(report_month, original_target_doc)
        row["planned_remaining_months"] = months_between(report_dt, orig_doc_dt)

        # revised_remaining_months: months_between(report_month, revised_doc)
        row["revised_remaining_months"] = months_between(report_dt, rev_doc_dt)

        # schedule_extension_months: months_between(original_target_doc, revised_doc)
        sched_ext = None
        if orig_doc_dt and rev_doc_dt:
            sched_ext = months_between(orig_doc_dt, rev_doc_dt)
        elif orig_doc_dt and not rev_doc_dt:
            sched_ext = 0
        row["schedule_extension_months"] = sched_ext

        # extension_rate_pct: (schedule_extension_months / original_duration_months) * 100
        ext_rate = None
        if sched_ext is not None and orig_dur is not None and orig_dur > 0:
            ext_rate = round((sched_ext / orig_dur) * 100.0, 2)
        row["extension_rate_pct"] = ext_rate

        # days_to_original_target: original_target_doc - report_month
        days_orig = None
        if orig_doc_dt and report_dt:
            days_orig = (orig_doc_dt - report_dt).days
        row["days_to_original_target"] = days_orig

        # days_to_revised_target: revised_doc - report_month
        days_rev = None
        if target_doc_dt and report_dt:
            days_rev = (target_doc_dt - report_dt).days
        row["days_to_revised_target"] = days_rev

        # overdue_days: if applicable target date has passed (target_date < report_month) -> days, else 0
        overdue = 0
        if target_doc_dt and report_dt:
            diff = (report_dt - target_doc_dt).days
            overdue = max(0, diff)
        row["overdue_days"] = overdue

        # schedule_status: COMPLETED, OVERDUE, EXTENDED, ON_TRACK, UNKNOWN
        if phys_prog is not None and phys_prog >= 100.0:
            sched_status = "COMPLETED"
        elif target_doc_dt and report_dt and (report_dt > target_doc_dt):
            sched_status = "OVERDUE"
        elif sched_ext is not None and sched_ext > 0:
            sched_status = "EXTENDED"
        elif target_doc_dt and report_dt and (report_dt <= target_doc_dt):
            sched_status = "ON_TRACK"
        else:
            sched_status = "UNKNOWN"
        row["schedule_status"] = sched_status

        # extension_count: count of revised target date changes in history
        ext_count = 0
        prev_rev = None
        for p in past_window:
            p_rev = p.get("revised_doc")
            if p_rev and p_rev != prev_rev:
                if prev_rev is not None:
                    ext_count += 1
                prev_rev = p_rev
        row["extension_count"] = ext_count if len(past_window) > 1 else None

        # -------------------------------------------------------------
        # 2. FINANCIAL DERIVED FEATURES
        # -------------------------------------------------------------
        # cost_escalation_crore: revised_cost_crore - original_cost_crore
        cost_esc = None
        if rev_cost is not None and orig_cost is not None:
            cost_esc = round(rev_cost - orig_cost, 2)
        row["cost_escalation_crore"] = cost_esc

        # cost_escalation_ratio: revised_cost_crore / original_cost_crore
        cost_esc_ratio = None
        if rev_cost is not None and orig_cost is not None and orig_cost > 0:
            cost_esc_ratio = round(rev_cost / orig_cost, 4)
        row["cost_escalation_ratio"] = cost_esc_ratio

        # remaining_budget_crore: revised_cost_crore - cumulative_expenditure_crore
        rem_budget = None
        if rev_cost is not None and cum_exp is not None:
            rem_budget = round(rev_cost - cum_exp, 2)
        row["remaining_budget_crore"] = rem_budget

        # cost_overrun_pct: ((revised_cost_crore - original_cost_crore) / original_cost_crore) * 100
        cost_overrun = None
        if orig_cost is not None and orig_cost > 0 and rev_cost is not None:
            cost_overrun = round(((rev_cost - orig_cost) / orig_cost) * 100.0, 2)
        row["cost_overrun_pct"] = cost_overrun

        # expenditure_ratio_pct: (cumulative_expenditure_crore / revised_cost_crore) * 100
        exp_ratio = None
        base_cost = rev_cost if (rev_cost and rev_cost > 0) else orig_cost
        if cum_exp is not None and base_cost and base_cost > 0:
            exp_ratio = round((cum_exp / base_cost) * 100.0, 2)
        row["expenditure_ratio_pct"] = exp_ratio

        # expenditure_velocity_crore_month: calculated from historical monthly expenditure changes
        exp_velocity = None
        if len(past_window) >= 2:
            prev_row = past_window[-2]
            prev_exp = prev_row.get("cumulative_expenditure_crore")
            prev_dt = parse_date(prev_row.get("report_month"))
            if cum_exp is not None and prev_exp is not None and report_dt and prev_dt:
                m_diff = months_between(prev_dt, report_dt)
                if m_diff and m_diff > 0:
                    exp_velocity = round((cum_exp - prev_exp) / m_diff, 2)
        row["expenditure_velocity_crore_month"] = exp_velocity

        # Update past_window[-1] with the partially enriched row so lag/trend computations can access current fields
        past_window_current = list(past_window[:-1]) + [row]

        # -------------------------------------------------------------
        # 3. PROGRESS DERIVED FEATURES & LAGS
        # -------------------------------------------------------------
        # remaining_work_pct: 100 - physical_progress_pct
        row["remaining_work_pct"] = round(100.0 - phys_prog, 2) if phys_prog is not None else None

        # Lag metrics: find observations ~1m, ~3m, ~6m prior
        row["physical_progress_delta_1m"] = self._compute_progress_delta(past_window_current, target_months_prior=1)
        row["physical_progress_delta_3m"] = self._compute_progress_delta(past_window_current, target_months_prior=3)
        row["physical_progress_delta_6m"] = self._compute_progress_delta(past_window_current, target_months_prior=6)

        # Velocity metrics
        row["progress_velocity_3m"] = self._compute_progress_velocity(past_window_current, window_months=3)
        row["progress_velocity_6m"] = self._compute_progress_velocity(past_window_current, window_months=6)

        # Trend slope
        row["progress_trend_slope"] = self._compute_progress_slope(past_window_current)

        # -------------------------------------------------------------
        # 4. PHYSICAL-FINANCIAL RELATIONSHIP & FLAGS
        # -------------------------------------------------------------
        # physical_financial_gap_pct: expenditure_ratio_pct - physical_progress_pct
        gap = None
        if exp_ratio is not None and phys_prog is not None:
            gap = round(exp_ratio - phys_prog, 2)
        row["physical_financial_gap_pct"] = gap

        # physical_to_expenditure_ratio: physical_progress_pct / expenditure_ratio_pct
        p_to_e = None
        if phys_prog is not None and exp_ratio is not None and exp_ratio > 0:
            p_to_e = round(phys_prog / exp_ratio, 4)
        row["physical_to_expenditure_ratio"] = p_to_e

        # progress_expenditure_mismatch_flag
        mismatch_flag = 0
        if gap is not None and gap > self.gap_threshold:
            mismatch_flag = 1
        row["progress_expenditure_mismatch_flag"] = mismatch_flag

        # high_expenditure_low_progress_flag
        high_low_flag = 0
        if exp_ratio is not None and phys_prog is not None:
            if exp_ratio >= self.high_exp_threshold and phys_prog <= self.low_prog_threshold:
                high_low_flag = 1
        row["high_expenditure_low_progress_flag"] = high_low_flag

        # -------------------------------------------------------------
        # 5. COST & EXPENDITURE TRENDS
        # -------------------------------------------------------------
        past_window_current = list(past_window[:-1]) + [row]
        row["cost_overrun_delta_1m"] = self._compute_metric_delta(past_window_current, "cost_overrun_pct", 1)
        row["cost_overrun_delta_3m"] = self._compute_metric_delta(past_window_current, "cost_overrun_pct", 3)
        row["cost_overrun_trend_slope"] = self._compute_metric_slope(past_window_current, "cost_overrun_pct")

        row["expenditure_ratio_delta_1m"] = self._compute_metric_delta(past_window_current, "expenditure_ratio_pct", 1)
        row["expenditure_ratio_delta_3m"] = self._compute_metric_delta(past_window_current, "expenditure_ratio_pct", 3)

        row["schedule_extension_delta_1m"] = self._compute_metric_delta(past_window_current, "schedule_extension_months", 1)

        # -------------------------------------------------------------
        # 6. RISK SIGNAL COUNT
        # -------------------------------------------------------------
        risk_signals = 0
        # Condition 1: Progress stagnation (3m progress change <= stagnation threshold when 3m history exists)
        if row["physical_progress_delta_3m"] is not None and row["physical_progress_delta_3m"] < self.stagnation_threshold:
            risk_signals += 1
        # Condition 2: Progress expenditure mismatch
        if mismatch_flag == 1:
            risk_signals += 1
        # Condition 3: High expenditure / low progress
        if high_low_flag == 1:
            risk_signals += 1
        # Condition 4: Increasing cost overrun
        if row["cost_overrun_delta_1m"] is not None and row["cost_overrun_delta_1m"] > 0:
            risk_signals += 1
        elif cost_overrun is not None and cost_overrun > self.cost_overrun_warning:
            risk_signals += 1
        # Condition 5: Schedule extended
        if sched_status == "EXTENDED":
            risk_signals += 1
        # Condition 6: Overdue
        if sched_status == "OVERDUE":
            risk_signals += 1

        row["risk_signal_count"] = risk_signals

        return row

    def _compute_progress_delta(self, past_window: List[Dict[str, Any]], target_months_prior: int) -> Optional[float]:
        """Find the snapshot approximately target_months_prior and compute progress delta."""
        if len(past_window) < 2:
            return None
        current_row = past_window[-1]
        current_prog = current_row.get("physical_progress_pct")
        current_dt = parse_date(current_row.get("report_month"))
        if current_prog is None or not current_dt:
            return None

        # Look for the historical row closest to target_months_prior
        best_match = None
        best_diff = 999
        for row in past_window[:-1]:
            row_prog = row.get("physical_progress_pct")
            row_dt = parse_date(row.get("report_month"))
            if row_prog is not None and row_dt:
                m_diff = months_between(row_dt, current_dt)
                if m_diff is not None and m_diff > 0:
                    diff_from_target = abs(m_diff - target_months_prior)
                    # Allow tolerance of +/- 1 month
                    if diff_from_target <= 1 and diff_from_target < best_diff:
                        best_diff = diff_from_target
                        best_match = row_prog

        if best_match is not None:
            return round(current_prog - best_match, 2)
        return None

    def _compute_progress_velocity(self, past_window: List[Dict[str, Any]], window_months: int) -> Optional[float]:
        """Compute average monthly physical progress change over window_months."""
        if len(past_window) < 2:
            return None
        current_row = past_window[-1]
        current_prog = current_row.get("physical_progress_pct")
        current_dt = parse_date(current_row.get("report_month"))
        if current_prog is None or not current_dt:
            return None

        # Find earliest record in window
        earliest_prog = None
        earliest_m_diff = 0
        for row in reversed(past_window[:-1]):
            row_prog = row.get("physical_progress_pct")
            row_dt = parse_date(row.get("report_month"))
            if row_prog is not None and row_dt:
                m_diff = months_between(row_dt, current_dt)
                if m_diff and 1 <= m_diff <= (window_months + 1):
                    earliest_prog = row_prog
                    earliest_m_diff = m_diff

        if earliest_prog is not None and earliest_m_diff > 0:
            return round((current_prog - earliest_prog) / earliest_m_diff, 2)
        return None

    def _compute_progress_slope(self, past_window: List[Dict[str, Any]]) -> Optional[float]:
        """Compute linear trend slope from available historical physical progress values."""
        points = []
        base_dt = None
        for row in past_window:
            prog = row.get("physical_progress_pct")
            dt = parse_date(row.get("report_month"))
            if prog is not None and dt:
                if base_dt is None:
                    base_dt = dt
                m_offset = months_between(base_dt, dt)
                points.append((m_offset, float(prog)))

        if len(points) < self.min_slope_obs:
            return None

        x_vals = [p[0] for p in points]
        y_vals = [p[1] for p in points]
        return compute_linear_slope(y_vals, x_vals)

    def _compute_metric_delta(self, past_window: List[Dict[str, Any]], metric_name: str, target_months_prior: int) -> Optional[float]:
        """Compute delta for a generic metric."""
        if len(past_window) < 2:
            return None
        current_row = past_window[-1]
        current_val = current_row.get(metric_name)
        current_dt = parse_date(current_row.get("report_month"))
        if current_val is None or not current_dt:
            return None

        best_match = None
        best_diff = 999
        for row in past_window[:-1]:
            val = row.get(metric_name)
            dt = parse_date(row.get("report_month"))
            if val is not None and dt:
                m_diff = months_between(dt, current_dt)
                if m_diff and m_diff > 0:
                    diff_from_target = abs(m_diff - target_months_prior)
                    if diff_from_target <= 1 and diff_from_target < best_diff:
                        best_diff = diff_from_target
                        best_match = float(val)

        if best_match is not None:
            return round(float(current_val) - best_match, 2)
        return None

    def _compute_metric_slope(self, past_window: List[Dict[str, Any]], metric_name: str) -> Optional[float]:
        """Compute linear slope for a generic metric."""
        points = []
        base_dt = None
        for row in past_window:
            val = row.get(metric_name)
            dt = parse_date(row.get("report_month"))
            if val is not None and dt:
                if base_dt is None:
                    base_dt = dt
                m_offset = months_between(base_dt, dt)
                points.append((m_offset, float(val)))

        if len(points) < self.min_slope_obs:
            return None

        x_vals = [p[0] for p in points]
        y_vals = [p[1] for p in points]
        return compute_linear_slope(y_vals, x_vals)
