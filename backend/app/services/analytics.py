"""services/analytics.py
======================
High-performance, deterministic Analytics Engine for InsightForge AI.

Executes structured analytical calculations over cleaned or raw datasets:
  1. Business KPI Overview
  2. Multi-dimensional parameterized Aggregation
  3. Time-Series Resampling with Rolling Windows & Cumulative Growth
  4. Segment Breakdown with Contribution Percentages
  5. 2D Cross-Tabulation Contingency Tables
  6. Correlation Matrices with Strict Undefined Handling
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.core.storage import get_processed_path, get_upload_path, validate_path_containment
from app.db.models.dataset import Dataset
from app.schemas.analytics import (
    AggregationQuery,
    AggregationResult,
    BreakdownItem,
    BreakdownQuery,
    BreakdownResult,
    CorrelationQuery,
    CorrelationResult,
    CrossTabQuery,
    CrossTabResult,
    DatasetOverviewResponse,
    FilterClause,
    MetricSpec,
    TimeSeriesPoint,
    TimeSeriesQuery,
    TimeSeriesResult,
)
from app.services.profiler import _CONTINUOUS_METRIC_PATTERNS, _DATE_NAME_PATTERNS, load_dataset_dataframe
from app.services.cleaner import normalize_column_name



# ---------------------------------------------------------------------------
# Path Containment & Dataset Loading
# ---------------------------------------------------------------------------

def resolve_and_load_dataset(dataset: Dataset) -> tuple[pd.DataFrame, bool]:
    """Securely resolve and load the dataset file, prioritizing cleaned artifacts.

    Returns:
        tuple: (DataFrame, is_cleaned: bool)

    Raises:
        ValueError: If path containment check fails.
        FileNotFoundError: If neither processed nor raw files exist on disk.
    """
    settings = get_settings()

    # 1. Check for Phase 8 processed path
    if dataset.processed_path:
        expected_processed_dir = Path(settings.processed_dir).resolve() / str(dataset.organization_id)
        raw_proc = str(dataset.processed_path).strip()
        if "\x00" in raw_proc or ".." in raw_proc:
            raise ValueError(f"Security error: Unsafe characters or traversal detected in processed_path: '{raw_proc}'")

        if Path(raw_proc).is_absolute():
            safe_processed_path = validate_path_containment(raw_proc, expected_processed_dir)
        else:
            # Canonical processed location for this dataset
            canonical_proc = get_processed_path(dataset.organization_id, dataset.id, "csv")
            safe_processed_path = validate_path_containment(canonical_proc, expected_processed_dir)

        if safe_processed_path.exists() and safe_processed_path.is_file():
            df = pd.read_csv(safe_processed_path)

            # Phase 8 cleaning normalizes column headers to snake_case.
            # The profile API exposes the original uploaded column names.
            # Restore the original names when the processed artifact matches
            # the normalized form of the raw dataset columns.
            try:
                raw_upload_dir = Path(settings.upload_dir).resolve() / str(dataset.organization_id)
                canonical_raw = get_upload_path(
                    dataset.organization_id,
                    dataset.id,
                    dataset.file_type,
                )
                safe_raw_path = validate_path_containment(
                    canonical_raw,
                    raw_upload_dir,
                )

                if safe_raw_path.exists() and safe_raw_path.is_file():
                    raw_df = load_dataset_dataframe(
                        safe_raw_path,
                        dataset.file_type,
                    )

                    raw_columns = [str(c) for c in raw_df.columns]
                    processed_columns = [str(c) for c in df.columns]

                    if (
                        len(raw_columns) == len(processed_columns)
                        and raw_columns != processed_columns
                    ):
                        normalized_to_original: dict[str, str] = {}
                        collision = False

                        for original in raw_columns:
                            normalized = normalize_column_name(original)

                            if (
                                normalized in normalized_to_original
                                and normalized_to_original[normalized] != original
                            ):
                                collision = True
                                break

                            normalized_to_original[normalized] = original

                        if (
                            not collision
                            and all(
                                column in normalized_to_original
                                for column in processed_columns
                            )
                        ):
                            df.columns = [
                                normalized_to_original[column]
                                for column in processed_columns
                            ]
            except (FileNotFoundError, ValueError):
                # If the raw artifact cannot be loaded, keep the processed
                # dataframe unchanged rather than breaking analytics.
                pass

            return df, True

    # 2. Fallback to raw upload storage_path
    if not dataset.storage_path:
        raise FileNotFoundError(f"Dataset {dataset.id} has no storage_path configured.")

    expected_upload_dir = Path(settings.upload_dir).resolve() / str(dataset.organization_id)
    raw_storage = str(dataset.storage_path).strip()
    if "\x00" in raw_storage or ".." in raw_storage:
        raise ValueError(f"Security error: Unsafe characters or traversal detected in storage_path: '{raw_storage}'")

    if Path(raw_storage).is_absolute():
        safe_upload_path = validate_path_containment(raw_storage, expected_upload_dir)
    else:
        canonical_upload = get_upload_path(dataset.organization_id, dataset.id, dataset.file_type)
        safe_upload_path = validate_path_containment(canonical_upload, expected_upload_dir)

    if not safe_upload_path.exists() or not safe_upload_path.is_file():
        raise FileNotFoundError(f"Dataset file does not exist on disk at: {safe_upload_path}")

    df = load_dataset_dataframe(safe_upload_path, dataset.file_type)
    return df, False


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------

def validate_columns(df: pd.DataFrame, requested_columns: list[str]) -> None:
    """Ensure all requested columns exist in the DataFrame."""
    available = set(df.columns)
    for col in requested_columns:
        if col not in available:
            raise ValueError(
                f"Column '{col}' does not exist in dataset. Available columns: {sorted(list(available))}"
            )


def validate_metric_compatibility(df: pd.DataFrame, metrics: list[MetricSpec]) -> None:
    """Validate that metrics are mathematically compatible with column datatypes."""
    for m in metrics:
        validate_columns(df, [m.column])
        series = df[m.column]
        is_numeric = pd.api.types.is_numeric_dtype(series)
        is_datetime = pd.api.types.is_datetime64_any_dtype(series)

        if m.aggregation in ("sum", "mean", "median", "std"):
            if not is_numeric:
                raise ValueError(
                    f"Aggregation '{m.aggregation}' is not supported on non-numeric column '{m.column}' "
                    f"(type: '{series.dtype}'). Numeric aggregations require integer or float columns."
                )

        elif m.aggregation in ("min", "max"):
            if not (is_numeric or is_datetime):
                # Check if strings can parse as dates or numbers
                coerced = pd.to_numeric(series, errors="coerce")
                if coerced.notna().sum() / max(1, len(series)) < 0.70:
                    raise ValueError(
                        f"Aggregation '{m.aggregation}' is not supported on non-numeric/non-datetime column '{m.column}'."
                    )

        elif m.aggregation == "count":
            # count is valid on any column
            pass


def validate_date_column(df: pd.DataFrame, date_column: str) -> pd.Series:
    """Verify that date_column contains valid datetime data and return parsed Series."""
    validate_columns(df, [date_column])
    series = df[date_column]

    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        raise ValueError(
            f"Column '{date_column}' is numeric/boolean and cannot be used as a datetime column."
        )

    # Attempt string parsing
    non_null = series.dropna().astype(str)
    if len(non_null) == 0:
        raise ValueError(f"Date column '{date_column}' contains only null values.")

    sample = non_null.head(100)
    parsed_sample = pd.to_datetime(sample, errors="coerce", format="mixed")
    valid_ratio = parsed_sample.notna().sum() / max(1, len(sample))

    if valid_ratio < 0.70:
        raise ValueError(
            f"Column '{date_column}' is not a valid datetime column. Valid date ratio: {round(valid_ratio * 100, 1)}%."
        )

    return pd.to_datetime(series, errors="coerce", format="mixed")


# ---------------------------------------------------------------------------
# Filter Engine
# ---------------------------------------------------------------------------

def apply_filters(df: pd.DataFrame, filters: list[FilterClause]) -> pd.DataFrame:
    """Apply row-level filter expressions safely with vectorized evaluation."""
    if not filters:
        return df

    filtered_df = df.copy()
    for f in filters:
        validate_columns(filtered_df, [f.column])
        col = filtered_df[f.column]

        if f.operator == "eq":
            filtered_df = filtered_df[col.astype(str) == str(f.value)]

        elif f.operator == "neq":
            filtered_df = filtered_df[col.astype(str) != str(f.value)]

        elif f.operator in ("gt", "gte", "lt", "lte"):
            try:
                num_val = float(f.value)
                num_col = pd.to_numeric(col, errors="coerce")
                if f.operator == "gt":
                    filtered_df = filtered_df[num_col > num_val]
                elif f.operator == "gte":
                    filtered_df = filtered_df[num_col >= num_val]
                elif f.operator == "lt":
                    filtered_df = filtered_df[num_col < num_val]
                elif f.operator == "lte":
                    filtered_df = filtered_df[num_col <= num_val]
            except (ValueError, TypeError):
                raise ValueError(
                    f"Operator '{f.operator}' on column '{f.column}' requires a numeric comparison value, got '{f.value}'."
                )

        elif f.operator == "in":
            if not isinstance(f.value, list) or len(f.value) == 0:
                raise ValueError(f"Operator 'in' on column '{f.column}' requires a non-empty list of values.")
            str_vals = {str(x) for x in f.value}
            filtered_df = filtered_df[col.astype(str).isin(str_vals)]

        elif f.operator == "between":
            if not isinstance(f.value, list) or len(f.value) != 2:
                raise ValueError(f"Operator 'between' on column '{f.column}' requires a list of exactly two [min, max] values.")
            try:
                min_v = float(f.value[0])
                max_v = float(f.value[1])
                if min_v > max_v:
                    min_v, max_v = max_v, min_v
                num_col = pd.to_numeric(col, errors="coerce")
                filtered_df = filtered_df[(num_col >= min_v) & (num_col <= max_v)]
            except (ValueError, TypeError):
                raise ValueError(
                    f"Operator 'between' on column '{f.column}' requires numeric [min, max] bounds, got {f.value}."
                )

    return filtered_df


# ---------------------------------------------------------------------------
# Core Analytical Operations
# ---------------------------------------------------------------------------

def compute_overview(
    df: pd.DataFrame, dataset_id: UUID, is_cleaned: bool
) -> DatasetOverviewResponse:
    """Compute high-level summary KPIs, temporal bounds, and key dimensional previews."""
    row_count = len(df)
    col_count = len(df.columns)

    numeric_kpis: dict[str, dict[str, float]] = {}
    temporal_kpi: dict[str, Any] | None = None
    top_dimension_kpis: dict[str, list[dict[str, Any]]] = {}

    # Numeric KPIs (capped at 50 numeric columns)
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])][:50]
    for c in num_cols:
        series = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(series) > 0:
            numeric_kpis[c] = {
                "sum": round(float(series.sum()), 4),
                "mean": round(float(series.mean()), 4),
                "median": round(float(series.median()), 4),
                "min": round(float(series.min()), 4),
                "max": round(float(series.max()), 4),
                "std": round(float(series.std()), 4) if len(series) > 1 else 0.0,
            }

    # Temporal KPI (detect best date column)
    date_cols = [c for c in df.columns if _DATE_NAME_PATTERNS.search(str(c)) or pd.api.types.is_datetime64_any_dtype(df[c])]
    if date_cols:
        best_date_col = date_cols[0]
        try:
            dt_series = pd.to_datetime(df[best_date_col], errors="coerce", format="mixed").dropna()
            if len(dt_series) > 0:
                min_dt = dt_series.min()
                max_dt = dt_series.max()
                temporal_kpi = {
                    "column": best_date_col,
                    "min_date": min_dt.strftime("%Y-%m-%d"),
                    "max_date": max_dt.strftime("%Y-%m-%d"),
                    "date_range_days": max(0, (max_dt - min_dt).days),
                }
        except Exception:
            temporal_kpi = None

    # Top Dimension KPIs (up to 5 categorical columns, top 10 categories each)
    cat_cols = [
        c for c in df.columns
        if c not in num_cols and not (date_cols and c == date_cols[0])
    ][:5]

    for c in cat_cols:
        val_counts = df[c].dropna().astype(str).value_counts().head(10)
        items = []
        tot = max(1, len(df[c].dropna()))
        for cat_name, cnt in val_counts.items():
            items.append({
                "category": cat_name,
                "count": int(cnt),
                "percentage": round((cnt / tot) * 100.0, 2),
            })
        if items:
            top_dimension_kpis[c] = items

    return DatasetOverviewResponse(
        dataset_id=dataset_id,
        is_cleaned=is_cleaned,
        row_count=row_count,
        column_count=col_count,
        numeric_kpis=numeric_kpis,
        temporal_kpi=temporal_kpi,
        top_dimension_kpis=top_dimension_kpis,
    )


def run_aggregation(
    df: pd.DataFrame, dataset_id: UUID, is_cleaned: bool, query: AggregationQuery
) -> AggregationResult:
    """Execute multi-dimensional grouping and metric aggregation with sorting and pagination."""
    # 1. Validation
    validate_columns(df, query.dimensions)
    validate_metric_compatibility(df, query.metrics)

    # 2. Filter
    filtered_df = apply_filters(df, query.filters)
    total_rows = len(filtered_df)

    if total_rows == 0:
        return AggregationResult(
            dataset_id=dataset_id,
            is_cleaned=is_cleaned,
            total_rows=0,
            data=[],
        )

    # Metric aggregation mapping
    def _agg_series(ser: pd.Series, agg: str) -> float:
        if agg == "count":
            return float(len(ser.dropna()))
        ser_clean = pd.to_numeric(ser, errors="coerce").dropna()
        if len(ser_clean) == 0:
            return 0.0
        if agg == "sum":
            return float(round(ser_clean.sum(), 4))
        if agg == "mean":
            return float(round(ser_clean.mean(), 4))
        if agg == "median":
            return float(round(ser_clean.median(), 4))
        if agg == "min":
            return float(round(ser_clean.min(), 4))
        if agg == "max":
            return float(round(ser_clean.max(), 4))
        if agg == "std":
            return float(round(ser_clean.std(), 4)) if len(ser_clean) > 1 else 0.0
        return 0.0

    # 3. Aggregation execution
    allowed_order_cols = set(query.dimensions)
    metric_labels = []
    for m in query.metrics:
        label = m.alias if m.alias else f"{m.column}_{m.aggregation}"
        metric_labels.append(label)
        allowed_order_cols.add(label)

    # Validate order_by
    if query.order_by and query.order_by not in allowed_order_cols:
        raise ValueError(
            f"order_by column '{query.order_by}' is not in selected dimensions or metrics ({sorted(list(allowed_order_cols))})."
        )

    if not query.dimensions:
        # Scalar aggregation
        row_dict: dict[str, Any] = {}
        for m, label in zip(query.metrics, metric_labels):
            row_dict[label] = _agg_series(filtered_df[m.column], m.aggregation)
        return AggregationResult(
            dataset_id=dataset_id,
            is_cleaned=is_cleaned,
            total_rows=1,
            data=[row_dict],
        )

    # Grouped aggregation
    agg_dict = {}
    for m, label in zip(query.metrics, metric_labels):
        agg_name = "count" if m.aggregation == "count" else m.aggregation
        agg_dict[label] = pd.NamedAgg(column=m.column, aggfunc=agg_name)

    grouped_res = filtered_df.groupby(query.dimensions, dropna=False).agg(**agg_dict).reset_index()

    # Sorting
    sort_col = query.order_by if query.order_by else metric_labels[0]
    grouped_res = grouped_res.sort_values(by=sort_col, ascending=not query.order_desc)

    # Pagination bounds
    sliced = grouped_res.iloc[query.offset : query.offset + query.limit]

    # Convert to JSON-serializable records
    records: list[dict[str, Any]] = []
    for _, r in sliced.iterrows():
        rec = {}
        for k, v in r.to_dict().items():
            if pd.isna(v):
                rec[k] = None
            elif isinstance(v, (np.floating, float)):
                rec[k] = float(round(v, 4))
            elif isinstance(v, (np.integer, int)):
                rec[k] = int(v)
            else:
                rec[k] = str(v)
        records.append(rec)

    return AggregationResult(
        dataset_id=dataset_id,
        is_cleaned=is_cleaned,
        total_rows=len(grouped_res),
        data=records,
    )


def run_time_series(
    df: pd.DataFrame, dataset_id: UUID, is_cleaned: bool, query: TimeSeriesQuery
) -> TimeSeriesResult:
    """Resample temporal data with rolling averages, cumulative totals, and growth rates."""
    # 1. Validation
    validate_columns(df, [query.metric_column])
    validate_metric_compatibility(df, [MetricSpec(column=query.metric_column, aggregation=query.aggregation)])
    dt_series = validate_date_column(df, query.date_column)

    # 2. Filter
    filtered_df = apply_filters(df, query.filters)
    if len(filtered_df) == 0:
        return TimeSeriesResult(
            dataset_id=dataset_id,
            is_cleaned=is_cleaned,
            date_column=query.date_column,
            metric_column=query.metric_column,
            granularity=query.granularity,
            series=[],
        )

    # Align dates
    valid_dt = dt_series.loc[filtered_df.index]
    metric_vals = pd.to_numeric(filtered_df[query.metric_column], errors="coerce")

    ts_df = pd.DataFrame({"timestamp": valid_dt, "val": metric_vals}).dropna(subset=["timestamp"])
    if len(ts_df) == 0:
        return TimeSeriesResult(
            dataset_id=dataset_id,
            is_cleaned=is_cleaned,
            date_column=query.date_column,
            metric_column=query.metric_column,
            granularity=query.granularity,
            series=[],
        )

    ts_df = ts_df.set_index("timestamp").sort_index()

    # Frequency mapping
    freq_map = {
        "day": "D",
        "week": "W-MON",
        "month": "MS",
        "quarter": "QS",
        "year": "YS",
    }
    freq = freq_map[query.granularity]

    # Aggregation
    agg_func = query.aggregation if query.aggregation != "count" else "count"
    resampled = ts_df["val"].resample(freq).agg(agg_func).fillna(0.0)

    # Optional Rolling Average
    rolling_series = None
    if query.rolling_window and query.rolling_window > 1:
        rolling_series = resampled.rolling(window=query.rolling_window, min_periods=1).mean()

    # Optional Cumulative Value
    cumulative_series = None
    if query.include_cumulative:
        cumulative_series = resampled.cumsum()

    # Optional Growth Rate Percentage
    growth_series = None
    if query.include_growth:
        pct = resampled.pct_change() * 100.0
        pct = pct.replace([np.inf, -np.inf], np.nan)
        growth_series = pct

    # Format output points
    points: list[TimeSeriesPoint] = []
    for idx, val in resampled.items():
        ts_str = idx.strftime("%Y-%m-%d")
        roll_val = float(round(rolling_series[idx], 4)) if rolling_series is not None else None
        cum_val = float(round(cumulative_series[idx], 4)) if cumulative_series is not None else None
        growth_val = float(round(growth_series[idx], 2)) if growth_series is not None and pd.notna(growth_series[idx]) else None

        points.append(
            TimeSeriesPoint(
                timestamp=ts_str,
                value=float(round(val, 4)),
                rolling_average=roll_val,
                cumulative_value=cum_val,
                growth_rate_pct=growth_val,
            )
        )

    return TimeSeriesResult(
        dataset_id=dataset_id,
        is_cleaned=is_cleaned,
        date_column=query.date_column,
        metric_column=query.metric_column,
        granularity=query.granularity,
        series=points,
    )


def run_breakdown(
    df: pd.DataFrame, dataset_id: UUID, is_cleaned: bool, query: BreakdownQuery
) -> BreakdownResult:
    """Compute segment distribution with Top N ranking, contribution percentage, and 'Other' binning."""
    validate_columns(df, [query.dimension])
    if query.metric_column:
        validate_columns(df, [query.metric_column])
        validate_metric_compatibility(df, [MetricSpec(column=query.metric_column, aggregation=query.aggregation)])

    filtered_df = apply_filters(df, query.filters)
    if len(filtered_df) == 0:
        return BreakdownResult(
            dataset_id=dataset_id,
            is_cleaned=is_cleaned,
            dimension=query.dimension,
            metric=query.metric_column or "count",
            total_value=0.0,
            items=[],
        )

    # Group and aggregate
    if query.metric_column:
        metric_ser = pd.to_numeric(filtered_df[query.metric_column], errors="coerce")
        grouped = filtered_df.groupby(query.dimension)[query.metric_column].agg(query.aggregation)
    else:
        grouped = filtered_df.groupby(query.dimension).size()

    grouped = grouped.sort_values(ascending=False)
    total_val = float(grouped.sum())

    top_slice = grouped.head(query.top_n)
    items: list[BreakdownItem] = []

    for cat_name, val in top_slice.items():
        v_float = float(round(val, 4))
        pct = round((v_float / max(1e-9, total_val)) * 100.0, 2)
        items.append(BreakdownItem(category=str(cat_name), value=v_float, percentage_of_total=pct))

    # Optional 'Other' grouping
    if query.include_other and len(grouped) > query.top_n:
        other_val = float(round(grouped.iloc[query.top_n :].sum(), 4))
        other_pct = round((other_val / max(1e-9, total_val)) * 100.0, 2)
        items.append(BreakdownItem(category="Other", value=other_val, percentage_of_total=other_pct))

    return BreakdownResult(
        dataset_id=dataset_id,
        is_cleaned=is_cleaned,
        dimension=query.dimension,
        metric=query.metric_column or "count",
        total_value=round(total_val, 4),
        items=items,
    )


def run_crosstab(
    df: pd.DataFrame, dataset_id: UUID, is_cleaned: bool, query: CrossTabQuery
) -> CrossTabResult:
    """Generate a 2D contingency / pivot matrix with strict 50x50 category limits."""
    validate_columns(df, [query.row_dimension, query.column_dimension])
    if query.metric_column:
        validate_columns(df, [query.metric_column])
        validate_metric_compatibility(df, [MetricSpec(column=query.metric_column, aggregation=query.aggregation)])

    filtered_df = apply_filters(df, query.filters)
    if len(filtered_df) == 0:
        return CrossTabResult(
            dataset_id=dataset_id,
            is_cleaned=is_cleaned,
            row_dimension=query.row_dimension,
            column_dimension=query.column_dimension,
            row_values=[],
            column_values=[],
            matrix=[],
        )

    # Enforce 50 distinct value limit
    n_rows = filtered_df[query.row_dimension].nunique()
    n_cols = filtered_df[query.column_dimension].nunique()

    if n_rows > 50:
        raise ValueError(
            f"Cross-tabulation row dimension '{query.row_dimension}' exceeds the maximum allowed 50 distinct categories (found {n_rows}). "
            "Please apply filters to narrow the scope."
        )
    if n_cols > 50:
        raise ValueError(
            f"Cross-tabulation column dimension '{query.column_dimension}' exceeds the maximum allowed 50 distinct categories (found {n_cols}). "
            "Please apply filters to narrow the scope."
        )

    # Pivot / crosstab calculation
    if query.metric_column:
        agg = "mean" if query.aggregation == "mean" else query.aggregation
        ct = pd.crosstab(
            index=filtered_df[query.row_dimension],
            columns=filtered_df[query.column_dimension],
            values=pd.to_numeric(filtered_df[query.metric_column], errors="coerce"),
            aggfunc=agg,
        ).fillna(0.0)
    else:
        ct = pd.crosstab(
            index=filtered_df[query.row_dimension],
            columns=filtered_df[query.column_dimension],
        ).fillna(0.0)

    row_vals = [str(r) for r in ct.index.tolist()]
    col_vals = [str(c) for c in ct.columns.tolist()]
    matrix_vals = [[float(round(val, 4)) for val in row] for row in ct.values.tolist()]

    return CrossTabResult(
        dataset_id=dataset_id,
        is_cleaned=is_cleaned,
        row_dimension=query.row_dimension,
        column_dimension=query.column_dimension,
        row_values=row_vals,
        column_values=col_vals,
        matrix=matrix_vals,
    )


def run_correlation(
    df: pd.DataFrame, dataset_id: UUID, is_cleaned: bool, query: CorrelationQuery
) -> CorrelationResult:
    """Calculate pairwise Pearson or Spearman correlation with strict null for zero-variance."""
    if query.columns:
        validate_columns(df, query.columns)
        num_cols = query.columns
        for c in num_cols:
            if not pd.api.types.is_numeric_dtype(df[c]):
                raise ValueError(f"Column '{c}' is non-numeric and cannot be included in correlation matrix.")
    else:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])][:50]

    if len(num_cols) < 2:
        raise ValueError(
            f"At least 2 numeric columns are required to compute a correlation matrix (found {len(num_cols)})."
        )

    # Compute correlation
    corr_df = df[num_cols].corr(method=query.method)

    # Identify zero-variance / constant columns
    std_devs = df[num_cols].std()
    zero_var_cols = set(std_devs[std_devs == 0].index.tolist())

    matrix_dict: dict[str, dict[str, float | None]] = {}
    for c1 in num_cols:
        matrix_dict[c1] = {}
        for c2 in num_cols:
            if c1 == c2:
                matrix_dict[c1][c2] = 1.0 if c1 not in zero_var_cols else None
            elif c1 in zero_var_cols or c2 in zero_var_cols:
                # Undefined zero-variance correlation is strictly None, NOT 0.0
                matrix_dict[c1][c2] = None
            else:
                raw_val = corr_df.loc[c1, c2]
                if pd.isna(raw_val):
                    matrix_dict[c1][c2] = None
                else:
                    matrix_dict[c1][c2] = float(round(raw_val, 4))

    return CorrelationResult(
        dataset_id=dataset_id,
        is_cleaned=is_cleaned,
        columns=num_cols,
        correlation_matrix=matrix_dict,
    )
