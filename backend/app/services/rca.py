"""services/rca.py
================
Stateless Root-Cause Analysis (RCA) Engine for InsightForge AI.

Provides:
1. Deterministic baseline selection precedence and inclusive calendar-window alignment
2. Waterfall dimension decomposition and pre-truncation reconciliation
3. Exact statistical z-score evaluation with zero-variance safety handling
4. Multi-dimensional driver ranking with cardinality bounds and deterministic tie-breaking
5. Secondary metric elasticity and co-movement analysis
6. Traceable evidence bundle generation and deterministic template narrative
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd

from app.schemas.rca import (
    DimensionDriverBreakdown,
    RCAAnalyzeRequest,
    RCAResponse,
    SecondaryMetricImpact,
    SegmentDriver,
    StatisticalScore,
    WaterfallReconciliation,
)


def align_event_and_baseline_windows(
    df: pd.DataFrame,
    date_col: str,
    event_start: date | None,
    event_end: date | None,
    baseline_start: date | None,
    baseline_end: date | None,
    baseline_mode: str = "prior_period",
    anchor_date: date | None = None,
) -> tuple[date, date, date, date, str]:
    """Deterministically resolve inclusive event and baseline calendar date boundaries.

    Precedence:
    1. Explicit custom baseline (baseline_start and baseline_end provided).
    2. Linked anomaly anchor date (anchor_date provided -> 1-day event, prior 1-day baseline).
    3. Explicit event window with auto-preceding baseline.
    4. Fallback earliest contiguous baseline if preceding window precedes dataset start.

    Returns:
        tuple[date, date, date, date, str]: (event_start, event_end, baseline_start, baseline_end, mode_used)
    """
    date_series = pd.to_datetime(df[date_col], errors="coerce").dropna().dt.date
    if len(date_series) == 0:
        raise ValueError(f"Date column '{date_col}' contains no parseable dates.")

    t_min = date_series.min()
    t_max = date_series.max()

    # Determine event window
    if event_start is None or event_end is None:
        if anchor_date is not None:
            ev_start = anchor_date
            ev_end = anchor_date
        else:
            raise ValueError("Event window could not be resolved; neither event dates nor anchor date provided.")
    else:
        ev_start = event_start
        ev_end = event_end

    if ev_start > ev_end:
        raise ValueError(f"'event_start' ({ev_start}) cannot be after 'event_end' ({ev_end}).")

    duration_days = (ev_end - ev_start).days + 1

    # Precedence 1: Explicit custom baseline
    if baseline_start is not None and baseline_end is not None:
        if baseline_start > baseline_end:
            raise ValueError(f"'baseline_start' ({baseline_start}) cannot be after 'baseline_end' ({baseline_end}).")
        if baseline_end >= ev_start and baseline_start <= ev_end:
            # Overlapping warning/error if fully identical
            if baseline_start == ev_start and baseline_end == ev_end:
                raise ValueError("Custom baseline window cannot be identical to the event window.")
        return ev_start, ev_end, baseline_start, baseline_end, "custom"

    # Precedence 2 & 3: Immediately preceding contiguous window of equal duration D
    base_end = ev_start - timedelta(days=1)
    base_start = base_end - timedelta(days=duration_days - 1)

    # Precedence 4: Fallback if base_start precedes dataset earliest date
    if base_start < t_min:
        # Check if there is an alternative non-overlapping contiguous window of duration D from t_min
        fallback_start = t_min
        fallback_end = fallback_start + timedelta(days=duration_days - 1)
        if fallback_end < ev_start:
            base_start = fallback_start
            base_end = fallback_end
            mode = "fallback_earliest"
        else:
            raise ValueError(
                f"Insufficient historical data to establish an equivalent non-overlapping baseline window of "
                f"{duration_days} days. Dataset earliest date is {t_min}, event starts on {ev_start}."
            )
    else:
        mode = "prior_period"

    return ev_start, ev_end, base_start, base_end, mode


def compute_statistical_z_score(
    baseline_values: list[float],
    event_val: float,
) -> StatisticalScore:
    """Compute exact statistical z-score: z_k = (y_k,event - mu_k,base) / sigma_k,base.

    Safely handles zero or near-zero variance.
    """
    n_base = len(baseline_values)
    if n_base == 0:
        return StatisticalScore(
            z_score=None,
            baseline_mean=0.0,
            baseline_std=None,
            is_significant=False,
            variance_note="No baseline observations available for variance estimation.",
        )

    mean_val = float(np.mean(baseline_values))
    if n_base < 2:
        return StatisticalScore(
            z_score=None,
            baseline_mean=round(mean_val, 4),
            baseline_std=None,
            is_significant=False,
            variance_note="Insufficient baseline observations (N < 2) for standard deviation estimation.",
        )

    std_val = float(np.std(baseline_values, ddof=1))

    # Zero or near-zero variance handling
    if std_val < 1e-6:
        diff = abs(event_val - mean_val)
        if diff < 1e-6:
            return StatisticalScore(
                z_score=0.0,
                baseline_mean=round(mean_val, 4),
                baseline_std=0.0,
                is_significant=False,
                variance_note="Baseline variance is zero; observed event value matches baseline constant.",
            )
        else:
            return StatisticalScore(
                z_score=None,
                baseline_mean=round(mean_val, 4),
                baseline_std=0.0,
                is_significant=True,
                variance_note="Zero baseline variance; deterministic step shift detected from constant baseline.",
            )

    z = (event_val - mean_val) / std_val
    is_sig = abs(z) >= 2.0

    return StatisticalScore(
        z_score=round(z, 4),
        baseline_mean=round(mean_val, 4),
        baseline_std=round(std_val, 4),
        is_significant=is_sig,
        variance_note=None,
    )


def compute_root_cause_analysis(
    df: pd.DataFrame,
    req: RCAAnalyzeRequest,
    dataset_id: UUID,
    anchor_date: date | None = None,
) -> RCAResponse:
    """Execute stateless, deterministic Root-Cause Analysis.

    Returns:
        RCAResponse: Complete evidence bundle with waterfall reconciliation and narrative.
    """
    date_col = req.date_column
    metric_col = req.metric_column

    if not date_col or date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' does not exist in dataset.")
    if not metric_col or metric_col not in df.columns:
        raise ValueError(f"Metric column '{metric_col}' does not exist in dataset.")

    # 1. Align event and baseline windows
    ev_start, ev_end, base_start, base_end, base_mode = align_event_and_baseline_windows(
        df=df,
        date_col=date_col,
        event_start=req.event_start,
        event_end=req.event_end,
        baseline_start=req.baseline_start,
        baseline_end=req.baseline_end,
        baseline_mode=req.baseline_mode,
        anchor_date=anchor_date,
    )

    ev_duration = (ev_end - ev_start).days + 1
    base_duration = (base_end - base_start).days + 1

    # 2. Slice dataframe into baseline and event sets
    # Parse dates safely to calendar date component
    parsed_dates = pd.to_datetime(df[date_col], errors="coerce").dt.date
    metric_series = pd.to_numeric(df[metric_col], errors="coerce")

    valid_mask = parsed_dates.notna() & metric_series.notna()
    clean_df = df[valid_mask].copy()
    clean_dates = parsed_dates[valid_mask]
    clean_df["_rca_date"] = clean_dates
    clean_df["_rca_metric"] = metric_series[valid_mask]

    base_mask = (clean_dates >= base_start) & (clean_dates <= base_end)
    event_mask = (clean_dates >= ev_start) & (clean_dates <= ev_end)

    df_base = clean_df[base_mask]
    df_event = clean_df[event_mask]

    if len(df_event) == 0:
        raise ValueError(f"No valid records found in event window [{ev_start}, {ev_end}].")
    if len(df_base) == 0:
        raise ValueError(f"No valid records found in baseline window [{base_start}, {base_end}].")

    # 3. Calculate primary metric totals
    agg = req.aggregation
    if agg == "sum":
        raw_event_val = float(df_event["_rca_metric"].sum())
        raw_base_val = float(df_base["_rca_metric"].sum())
        # Scale baseline if durations differ to compare like-for-like
        scale_factor = float(ev_duration) / float(base_duration)
        base_val = raw_base_val * scale_factor
        event_val = raw_event_val
    elif agg == "avg":
        base_val = float(df_base["_rca_metric"].mean())
        event_val = float(df_event["_rca_metric"].mean())
    elif agg == "count":
        raw_event_val = float(len(df_event))
        raw_base_val = float(len(df_base))
        scale_factor = float(ev_duration) / float(base_duration)
        base_val = raw_base_val * scale_factor
        event_val = raw_event_val
    else:
        raise ValueError(f"Unsupported aggregation '{agg}'.")

    total_delta = event_val - base_val
    pct_change = ((total_delta) / max(abs(base_val), 1e-6)) * 100.0

    # Check zero net change
    is_zero_net_change = abs(total_delta) < 1e-6
    if is_zero_net_change:
        contrib_status = "undefined_zero_net_change"
        contrib_expl = (
            "Total metric change is zero; individual segment contribution percentages are undefined, "
            "but compensating positive and negative sub-segment shifts are reported."
        )
    else:
        contrib_status = "ok"
        contrib_expl = None

    # 4. Resolve dimension columns
    available_dims = req.dimension_columns
    if not available_dims:
        # Auto-detect categorical columns
        detected = []
        for c in clean_df.columns:
            if c in (date_col, metric_col, "_rca_date", "_rca_metric"):
                continue
            # Check cardinality: must be between 2 and len(clean_df) // 2
            n_uniq = clean_df[c].nunique(dropna=True)
            if 2 <= n_uniq <= 500 and (clean_df[c].dtype == object or clean_df[c].dtype.name in ("category", "string", "bool")):
                detected.append(c)
        available_dims = detected[: req.max_dimensions]

    if not available_dims:
        available_dims = []

    # 5. Waterfall driver decomposition per dimension
    dimension_breakdowns: list[DimensionDriverBreakdown] = []
    all_drivers: list[SegmentDriver] = []
    total_segments_full_count = 0
    sum_deltas_full = 0.0

    for dim in available_dims:
        if dim not in clean_df.columns:
            continue

        # Cardinality handling: cap at top 20 categories by overall volume
        combined_counts = clean_df[dim].astype(str).value_counts()
        top_categories = set(combined_counts.head(20).index)

        def normalize_category(val: Any) -> str:
            s = str(val) if pd.notna(val) else "Unknown"
            return s if s in top_categories else "Other"

        # Apply grouping on base and event
        cat_base = df_base[dim].apply(normalize_category)
        cat_event = df_event[dim].apply(normalize_category)

        if agg == "sum":
            b_grouped = df_base.groupby(cat_base)["_rca_metric"].sum() * (float(ev_duration) / float(base_duration))
            e_grouped = df_event.groupby(cat_event)["_rca_metric"].sum()
        elif agg == "avg":
            b_grouped = df_base.groupby(cat_base)["_rca_metric"].mean()
            e_grouped = df_event.groupby(cat_event)["_rca_metric"].mean()
        else:
            b_grouped = df_base.groupby(cat_base)["_rca_metric"].count() * (float(ev_duration) / float(base_duration))
            e_grouped = df_event.groupby(cat_event)["_rca_metric"].count()

        all_cats = sorted(set(b_grouped.index).union(set(e_grouped.index)))
        dim_drivers: list[SegmentDriver] = []

        # Pre-compute time-series for z-scores per category over baseline dates
        # Group by [date, category] for daily variance
        daily_base = df_base.groupby([df_base["_rca_date"], cat_base])["_rca_metric"]
        if agg == "sum":
            daily_b_series = daily_base.sum().unstack(fill_value=0.0)
        elif agg == "avg":
            daily_b_series = daily_base.mean().unstack(fill_value=0.0)
        else:
            daily_b_series = daily_base.count().unstack(fill_value=0.0)

        for cat in all_cats:
            b_sub = float(b_grouped.get(cat, 0.0))
            e_sub = float(e_grouped.get(cat, 0.0))
            d_sub = e_sub - b_sub
            growth = ((d_sub) / max(abs(b_sub), 1e-6)) * 100.0

            if not is_zero_net_change:
                c_pct = round((d_sub / total_delta) * 100.0, 2)
            else:
                c_pct = None

            # Baseline daily values for z-score
            cat_daily_vals = daily_b_series[cat].tolist() if cat in daily_b_series.columns else []
            stat_score = compute_statistical_z_score(cat_daily_vals, e_sub)

            driver = SegmentDriver(
                dataset_id=dataset_id,
                anomaly_id=req.anomaly_id,
                dimension=dim,
                segment_value=cat,
                baseline_value=round(b_sub, 4),
                event_value=round(e_sub, 4),
                delta=round(d_sub, 4),
                contribution_pct=c_pct,
                growth_pct=round(growth, 2),
                statistical_score=stat_score,
                event_window={"start": ev_start.isoformat(), "end": ev_end.isoformat()},
                baseline_window={"start": base_start.isoformat(), "end": base_end.isoformat()},
                metric_name=metric_col,
            )
            dim_drivers.append(driver)
            all_drivers.append(driver)

        # Track reconciliation on the primary/first dimension decomposition
        if dim == available_dims[0]:
            sum_deltas_full = sum(d.delta for d in dim_drivers)
            total_segments_full_count = len(dim_drivers)

        # Sort drivers deterministically: descending abs(delta), tie-breaker ascending segment_value
        dim_drivers.sort(key=lambda d: (-abs(d.delta), d.segment_value))

        pos_drivers = [d for d in dim_drivers if d.delta > 0][: req.top_k_drivers]
        neg_drivers = [d for d in dim_drivers if d.delta < 0][: req.top_k_drivers]
        displayed_sum = sum(abs(d.contribution_pct or 0.0) for d in (pos_drivers + neg_drivers))

        dimension_breakdowns.append(
            DimensionDriverBreakdown(
                dimension=dim,
                total_segments=len(dim_drivers),
                top_positive_drivers=pos_drivers,
                top_negative_drivers=neg_drivers,
                coverage_pct=round(displayed_sum, 2),
            )
        )

    # 6. Waterfall Reconciliation check (pre-truncation)
    if available_dims:
        discrepancy = round(abs(total_delta - sum_deltas_full), 4)
        tol = max(1e-4, 0.0005 * abs(total_delta))
        is_reconciled = discrepancy <= tol
        reconcile_warn = None if is_reconciled else f"Discrepancy {discrepancy} exceeds numerical tolerance {tol}."
    else:
        discrepancy = 0.0
        is_reconciled = True
        sum_deltas_full = total_delta
        total_segments_full_count = 0
        reconcile_warn = None

    reconciliation = WaterfallReconciliation(
        sum_segment_deltas_full=round(sum_deltas_full, 4),
        total_metric_delta=round(total_delta, 4),
        discrepancy=discrepancy,
        is_reconciled=is_reconciled,
        truncated_display_count=min(50, len(all_drivers)),
        total_segments_count=total_segments_full_count,
        reconciliation_warning=reconcile_warn,
    )

    # 7. Overall Top Primary Drivers (bounded at 50 max intersections)
    all_drivers.sort(key=lambda d: (-abs(d.delta), d.dimension, d.segment_value))
    primary_drivers = all_drivers[: min(50, req.top_k_drivers * 2)]

    # 8. Secondary Metrics Analysis & Elasticity
    secondary_impacts: list[SecondaryMetricImpact] = []
    sec_metrics = req.secondary_metrics
    if sec_metrics is None:
        # Auto-detect numeric columns
        auto_sec = []
        for c in clean_df.columns:
            if c not in (metric_col, date_col, "_rca_date", "_rca_metric") and pd.api.types.is_numeric_dtype(clean_df[c]):
                auto_sec.append(c)
        sec_metrics = auto_sec[:3]

    for sm in sec_metrics:
        if sm not in clean_df.columns or sm == metric_col:
            continue
        sm_series = pd.to_numeric(clean_df[sm], errors="coerce")
        b_sec_val = float(sm_series[base_mask].sum()) if agg == "sum" else float(sm_series[base_mask].mean())
        if agg in ("sum", "count"):
            b_sec_val *= float(ev_duration) / float(base_duration)
        e_sec_val = float(sm_series[event_mask].sum()) if agg == "sum" else float(sm_series[event_mask].mean())

        d_sec = e_sec_val - b_sec_val
        sec_growth = ((d_sec) / max(abs(b_sec_val), 1e-6)) * 100.0

        # Elasticity calculation
        if abs(pct_change) < 1e-6 or abs(base_val) < 1e-6:
            elast = None
            e_status = "undefined_zero_primary_change"
        elif abs(b_sec_val) < 1e-6:
            elast = None
            e_status = "undefined_zero_secondary_baseline"
        else:
            elast = round(sec_growth / pct_change, 4)
            e_status = "ok"

        if abs(d_sec) < 1e-6:
            direction = "neutral"
        elif (d_sec > 0 and total_delta > 0) or (d_sec < 0 and total_delta < 0):
            direction = "concordant"
        else:
            direction = "divergent"

        secondary_impacts.append(
            SecondaryMetricImpact(
                metric_name=sm,
                baseline_value=round(b_sec_val, 4),
                event_value=round(e_sec_val, 4),
                delta=round(d_sec, 4),
                growth_pct=round(sec_growth, 2),
                direction=direction,
                elasticity=elast,
                elasticity_status=e_status,
            )
        )

    # 9. Deterministic Template Narrative
    lines: list[str] = []
    lines.append(
        f"Root-Cause Analysis for '{metric_col}' ({agg}) over event window [{ev_start} to {ev_end}] "
        f"compared against baseline [{base_start} to {base_end}]."
    )
    lines.append(
        f"Total metric shifted by {total_delta:+,.2f} ({pct_change:+.2f}%) from baseline {base_val:,.2f} to {event_val:,.2f}."
    )

    if is_zero_net_change:
        lines.append("Note: Overall net delta is zero. Positive and negative sub-segment shifts balanced out.")

    if primary_drivers:
        top_d = primary_drivers[0]
        c_str = f"{top_d.contribution_pct:+.1f}%" if top_d.contribution_pct is not None else "N/A"
        z_str = f"z={top_d.statistical_score.z_score:.2f}" if top_d.statistical_score.z_score is not None else "z=N/A"
        lines.append(
            f"The primary driver was {top_d.dimension}='{top_d.segment_value}' accounting for {c_str} of the total change "
            f"(delta: {top_d.delta:+,.2f}, growth: {top_d.growth_pct:+.1f}%, {z_str})."
        )

        sig_drivers = [d for d in primary_drivers if d.statistical_score.is_significant]
        if sig_drivers:
            sig_names = ", ".join(f"{d.dimension}='{d.segment_value}'" for d in sig_drivers[:3])
            lines.append(f"Statistically significant segment shifts detected in: {sig_names}.")

    if secondary_impacts:
        sec_summaries = []
        for s in secondary_impacts:
            e_str = f", elasticity: {s.elasticity:.2f}" if s.elasticity is not None else ""
            sec_summaries.append(f"'{s.metric_name}' ({s.direction} {s.growth_pct:+.1f}%{e_str})")
        lines.append(f"Secondary metric co-movements: {'; '.join(sec_summaries)}.")

    lines.append(
        f"Reconciliation: Sum of drivers = {sum_deltas_full:+,.2f} vs Total delta = {total_delta:+,.2f} "
        f"(discrepancy: {discrepancy:.4f}, reconciled: {is_reconciled})."
    )

    narrative = " ".join(lines)

    provenance = {
        "dataset_id": str(dataset_id),
        "anomaly_id": str(req.anomaly_id) if req.anomaly_id else None,
        "date_column": date_col,
        "metric_column": metric_col,
        "aggregation": agg,
        "event_window": {"start": ev_start.isoformat(), "end": ev_end.isoformat(), "duration_days": ev_duration},
        "baseline_window": {"start": base_start.isoformat(), "end": base_end.isoformat(), "duration_days": base_duration},
        "baseline_mode_applied": base_mode,
        "dimensions_evaluated": available_dims,
        "secondary_metrics_evaluated": [s.metric_name for s in secondary_impacts],
        "total_records_analyzed": len(df_base) + len(df_event),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "deterministic_waterfall_decomposition_with_zscore_and_elasticity",
    }

    return RCAResponse(
        dataset_id=dataset_id,
        anomaly_id=req.anomaly_id,
        metric_name=metric_col,
        aggregation=agg,
        event_window={"start": ev_start, "end": ev_end, "duration_days": ev_duration, "value": round(event_val, 4)},
        baseline_window={"start": base_start, "end": base_end, "duration_days": base_duration, "value": round(base_val, 4)},
        total_delta=round(total_delta, 4),
        percentage_change=round(pct_change, 2),
        contribution_status=contrib_status,
        contribution_explanation=contrib_expl,
        reconciliation=reconciliation,
        primary_drivers=primary_drivers,
        dimension_breakdowns=dimension_breakdowns,
        secondary_metrics=secondary_impacts,
        narrative_summary=narrative,
        provenance=provenance,
    )
