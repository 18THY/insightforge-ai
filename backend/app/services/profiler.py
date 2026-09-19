"""services/profiler.py
====================
Reusable dataset profiling engine for InsightForge AI.

Analyzes CSV and XLSX datasets and generates:
  - Dataset dimensions, memory footprint, column inventories.
  - Column classification (numeric, categorical, datetime, boolean, text, identifier).
  - Datatype inference and null / uniqueness metrics.
  - Deep-dive statistics (percentiles for numeric, frequencies for categorical, date ranges for datetime).
  - Duplicate row analysis and missing value distributions.
  - Transparent, explainable Data Quality Score (0-100) with component metrics.
"""

from __future__ import annotations

import io
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd

from app.schemas.profile import (
    CategoricalStats,
    CategoryFrequency,
    ColumnProfile,
    DataQualityComponents,
    DataQualityMetrics,
    DataQualityScore,
    DatasetProfileResponse,
    DatetimeStats,
    NumericStats,
)

# ---------------------------------------------------------------------------
# Constants & Identifier Heuristic Patterns
# ---------------------------------------------------------------------------

_ID_NAME_PATTERNS = re.compile(r"(_id|id|_key|_uuid|_code|_number)$|^id_|^key_|^code_|^uuid_|^ref_", re.IGNORECASE)
_CONTINUOUS_METRIC_PATTERNS = re.compile(
    r"(price|cost|amount|spend|revenue|profit|margin|rate|ratio|percent|score|balance|total|weight|discount|salary|val|value)",
    re.IGNORECASE,
)
_DATE_NAME_PATTERNS = re.compile(
    r"(date|time|created|updated|launched|timestamp|period|dob|registered|_at)",
    re.IGNORECASE,
)
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_BOOLEAN_POSITIVE = {"true", "1", "yes", "y", "t"}
_BOOLEAN_NEGATIVE = {"false", "0", "no", "n", "f"}
_BOOLEAN_ALL = _BOOLEAN_POSITIVE | _BOOLEAN_NEGATIVE


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_dataset_dataframe(file_path: Path | str, file_type: str) -> pd.DataFrame:
    """Load CSV or XLSX dataset defensively into a pandas DataFrame.

    Raises:
        FileNotFoundError: If the file does not exist on disk.
        ValueError: If the file is empty, corrupted, or cannot be parsed.
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError("Dataset storage file not found.")

    if p.stat().st_size == 0:
        raise ValueError("Dataset is empty. File contains zero bytes.")

    ext = file_type.lower().lstrip(".")

    try:
        if ext == "csv":
            # Attempt UTF-8, fallback to latin-1 / cp1252
            try:
                df = pd.read_csv(p, encoding="utf-8", low_memory=False)
            except UnicodeDecodeError:
                df = pd.read_csv(p, encoding="latin-1", low_memory=False)
        elif ext == "xlsx":
            df = pd.read_excel(p, engine="openpyxl")
        else:
            raise ValueError(f"Unsupported file type for profiling: '{file_type}'.")
    except pd.errors.EmptyDataError as e:
        raise ValueError(f"Dataset is empty: {e}") from e
    except pd.errors.ParserError as e:
        raise ValueError(f"Malformed CSV file: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to parse dataset file: {e}") from e

    if df.empty or len(df.columns) == 0:
        raise ValueError("Dataset is empty. Cannot profile a dataset with zero rows or columns.")

    return df


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def _clean_val(v: Any) -> Any:
    """Convert numpy / pandas scalar to clean JSON-serializable native Python type."""
    if v is None or pd.isna(v):
        return None
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return float(round(v, 4))
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    return str(v)


def _detect_boolean_column(series: pd.Series) -> bool:
    """Determine if a series contains boolean data."""
    if pd.api.types.is_bool_dtype(series):
        return True

    non_null = series.dropna()
    if len(non_null) == 0:
        return False

    unique_vals = set(non_null.unique())
    if len(unique_vals) > 2:
        return False

    str_vals = {str(x).strip().lower() for x in unique_vals}
    return str_vals.issubset(_BOOLEAN_ALL)


def _detect_identifier_column(series: pd.Series, col_name: str) -> bool:
    """Determine if a column is likely an identifier using transparent heuristics."""
    clean_name = str(col_name).strip()
    name_matches = bool(_ID_NAME_PATTERNS.search(clean_name))
    is_continuous_metric = bool(_CONTINUOUS_METRIC_PATTERNS.search(clean_name))
    is_date_named = bool(_DATE_NAME_PATTERNS.search(clean_name))

    if is_continuous_metric or is_date_named:
        return False

    non_null = series.dropna()
    if len(non_null) == 0:
        return False

    total_rows = len(series)
    unique_count = series.nunique()

    # Name-based heuristic: ends with _id, id, _key, _uuid, _code, etc.
    if name_matches:
        # Check that values look like discrete IDs (integers, strings without long text)
        if pd.api.types.is_numeric_dtype(series):
            return True
        sample = [str(x) for x in non_null.head(20)]
        avg_len = sum(len(x) for x in sample) / max(1, len(sample))
        has_spaces = any(" " in x for x in sample)
        if avg_len <= 64 and not has_spaces:
            return True
        return False

    # Content-based heuristic (for columns without ID in name):
    # Only if 100% unique, short length, and matches UUID format or integer
    if unique_count == total_rows and total_rows > 1:
        if pd.api.types.is_integer_dtype(series):
            return True
        if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
            sample = [str(x).strip() for x in non_null.head(20)]
            if all(_UUID_PATTERN.match(x) for x in sample):
                return True

    return False


# ---------------------------------------------------------------------------
# Column Profiling Logic
# ---------------------------------------------------------------------------

def profile_column(series: pd.Series, col_name: str) -> tuple[ColumnProfile, int, int, int]:
    """Profile a single column.

    Returns:
        tuple: (ColumnProfile, inconsistent_cells, invalid_dates, suspicious_values)
    """
    total_len = len(series)
    null_count = int(series.isna().sum())
    null_pct = round((null_count / max(1, total_len)) * 100.0, 2)

    non_null = series.dropna()
    non_null_count = len(non_null)
    unique_count = int(series.nunique())
    unique_pct = round((unique_count / max(1, non_null_count)) * 100.0, 2) if non_null_count > 0 else 0.0

    # Extract sample values (up to 5 distinct non-null)
    sample_values = [_clean_val(v) for v in non_null.drop_duplicates().head(5).tolist()]

    inconsistent_cells = 0
    invalid_dates = 0
    suspicious_values = 0

    # 1. Identifier Check
    if _detect_identifier_column(series, col_name):
        classification = "identifier"
        inferred_datatype = "integer" if pd.api.types.is_integer_dtype(series) else "string"
        profile = ColumnProfile(
            name=col_name,
            inferred_datatype=inferred_datatype,
            classification=classification,
            null_count=null_count,
            null_percentage=null_pct,
            unique_count=unique_count,
            unique_percentage=unique_pct,
            sample_values=sample_values,
        )
        return profile, inconsistent_cells, invalid_dates, suspicious_values

    # 2. Boolean Check
    if _detect_boolean_column(series):
        classification = "boolean"
        inferred_datatype = "boolean"
        profile = ColumnProfile(
            name=col_name,
            inferred_datatype=inferred_datatype,
            classification=classification,
            null_count=null_count,
            null_percentage=null_pct,
            unique_count=unique_count,
            unique_percentage=unique_pct,
            sample_values=sample_values,
        )
        return profile, inconsistent_cells, invalid_dates, suspicious_values

    # 3. Datetime Check
    is_datetime = False
    parsed_dates = None
    if pd.api.types.is_datetime64_any_dtype(series):
        is_datetime = True
        parsed_dates = series
    elif non_null_count > 0 and not pd.api.types.is_numeric_dtype(series) and (
        _DATE_NAME_PATTERNS.search(str(col_name))
        or pd.api.types.is_string_dtype(series)
        or pd.api.types.is_object_dtype(series)
    ):
        # Test datetime parsing
        sample_check = non_null.head(50).astype(str)
        # Require presence of date separators (-, /, :) or name matching date patterns
        has_separators = any("-" in s or "/" in s or ":" in s for s in sample_check)
        is_named_date = bool(_DATE_NAME_PATTERNS.search(str(col_name)))
        if has_separators or is_named_date:
            try:
                converted_sample = pd.to_datetime(sample_check, errors="coerce", format="mixed")
                valid_sample_ratio = converted_sample.notna().sum() / max(1, len(sample_check))
                if valid_sample_ratio >= 0.70:
                    is_datetime = True
                    parsed_dates = pd.to_datetime(series.astype(str), errors="coerce", format="mixed")
            except Exception:
                is_datetime = False

    if is_datetime and parsed_dates is not None:
        classification = "datetime"
        inferred_datatype = "datetime"

        # Count invalid dates (original non-null that became NaT or out of reasonable bounds 1900-2099)
        valid_mask = parsed_dates.notna()
        raw_non_null_mask = series.notna()
        nat_count = int((raw_non_null_mask & (~valid_mask)).sum())

        valid_dates = parsed_dates[valid_mask]
        out_of_bounds = 0
        if len(valid_dates) > 0:
            out_of_bounds = int(((valid_dates.dt.year < 1900) | (valid_dates.dt.year > 2099)).sum())

        invalid_dates = nat_count + out_of_bounds

        min_date_str = None
        max_date_str = None
        range_days = None
        if len(valid_dates) > 0:
            min_dt = valid_dates.min()
            max_dt = valid_dates.max()
            min_date_str = min_dt.isoformat() if pd.notna(min_dt) else None
            max_date_str = max_dt.isoformat() if pd.notna(max_dt) else None
            if pd.notna(min_dt) and pd.notna(max_dt):
                range_days = max(0, (max_dt - min_dt).days)

        profile = ColumnProfile(
            name=col_name,
            inferred_datatype=inferred_datatype,
            classification=classification,
            null_count=null_count,
            null_percentage=null_pct,
            unique_count=unique_count,
            unique_percentage=unique_pct,
            sample_values=sample_values,
            datetime_stats=DatetimeStats(
                min_date=min_date_str,
                max_date=max_date_str,
                date_range_days=range_days,
                invalid_date_count=invalid_dates,
            ),
        )
        return profile, inconsistent_cells, invalid_dates, suspicious_values

    # 4. Numeric Check
    is_numeric = False
    num_series = None
    if pd.api.types.is_numeric_dtype(series):
        is_numeric = True
        num_series = series.astype(float)
    elif non_null_count > 0:
        # Check if strings can be coerced to numeric
        coerced = pd.to_numeric(series, errors="coerce")
        coerced_valid = coerced.notna().sum()
        if coerced_valid / max(1, non_null_count) >= 0.85:
            is_numeric = True
            num_series = coerced
            inconsistent_cells = int(non_null_count - coerced_valid)

    if is_numeric and num_series is not None:
        classification = "numeric"
        valid_nums = num_series.dropna()

        # Inferred type
        if len(valid_nums) > 0 and (valid_nums % 1 == 0).all():
            inferred_datatype = "integer"
        else:
            inferred_datatype = "float"

        if len(valid_nums) > 0:
            c_min = float(valid_nums.min())
            c_max = float(valid_nums.max())
            c_mean = float(round(valid_nums.mean(), 4))
            c_median = float(round(valid_nums.median(), 4))
            c_std = float(round(valid_nums.std(), 4)) if len(valid_nums) > 1 else None

            p25 = float(round(valid_nums.quantile(0.25), 4))
            p50 = float(round(valid_nums.quantile(0.50), 4))
            p75 = float(round(valid_nums.quantile(0.75), 4))

            # Suspicious values detection:
            # 1) Negative numbers where strictly positive expected (e.g. price, quantity, spend)
            if _CONTINUOUS_METRIC_PATTERNS.search(str(col_name)) or "qty" in str(col_name).lower():
                suspicious_values += int((valid_nums < 0).sum())
            # 2) Extreme statistical outliers (|z| > 5)
            if c_std and c_std > 0 and len(valid_nums) >= 20:
                z_scores = (valid_nums - c_mean).abs() / c_std
                suspicious_values += int((z_scores > 5.0).sum())

            num_stats = NumericStats(
                min=c_min,
                max=c_max,
                mean=c_mean,
                median=c_median,
                std_dev=c_std,
                percentiles={"p25": p25, "p50": p50, "p75": p75},
            )
        else:
            num_stats = NumericStats(
                min=0.0,
                max=0.0,
                mean=0.0,
                median=0.0,
                std_dev=None,
                percentiles={"p25": 0.0, "p50": 0.0, "p75": 0.0},
            )

        profile = ColumnProfile(
            name=col_name,
            inferred_datatype=inferred_datatype,
            classification=classification,
            null_count=null_count,
            null_percentage=null_pct,
            unique_count=unique_count,
            unique_percentage=unique_pct,
            sample_values=sample_values,
            numeric_stats=num_stats,
        )
        return profile, inconsistent_cells, invalid_dates, suspicious_values

    # 5. Categorical vs Text Check
    sample_str = [str(x) for x in non_null.head(50)]
    avg_char_len = sum(len(x) for x in sample_str) / max(1, len(sample_str))

    is_categorical = (
        unique_count <= 100
        or unique_pct <= 15.0
        or (avg_char_len <= 30 and unique_count <= 500)
    )

    if is_categorical:
        classification = "categorical"
        inferred_datatype = "string"

        # Calculate top categories
        val_counts = non_null.value_counts().head(10)
        top_cats = []
        for val, count in val_counts.items():
            pct = round((int(count) / max(1, non_null_count)) * 100.0, 2)
            top_cats.append(CategoryFrequency(value=str(val), count=int(count), percentage=pct))

        cat_stats = CategoricalStats(
            num_categories=unique_count,
            top_categories=top_cats,
        )

        profile = ColumnProfile(
            name=col_name,
            inferred_datatype=inferred_datatype,
            classification=classification,
            null_count=null_count,
            null_percentage=null_pct,
            unique_count=unique_count,
            unique_percentage=unique_pct,
            sample_values=sample_values,
            categorical_stats=cat_stats,
        )
    else:
        classification = "text"
        inferred_datatype = "string"
        profile = ColumnProfile(
            name=col_name,
            inferred_datatype=inferred_datatype,
            classification=classification,
            null_count=null_count,
            null_percentage=null_pct,
            unique_count=unique_count,
            unique_percentage=unique_pct,
            sample_values=sample_values,
        )

    return profile, inconsistent_cells, invalid_dates, suspicious_values


# ---------------------------------------------------------------------------
# Data Quality Scoring
# ---------------------------------------------------------------------------

def calculate_data_quality_score(
    df: pd.DataFrame,
    total_inconsistent_cells: int,
    total_invalid_dates: int,
    total_suspicious_values: int,
    total_datetime_values: int,
    total_numeric_values: int,
) -> DataQualityScore:
    """Compute transparent 5-dimensional data quality score (0-100)."""
    row_count = len(df)
    col_count = len(df.columns)
    total_cells = max(1, row_count * col_count)

    missing_cells = int(df.isna().sum().sum())
    missing_pct = round((missing_cells / total_cells) * 100.0, 2)

    duplicate_rows = int(df.duplicated().sum())
    dup_pct = round((duplicate_rows / max(1, row_count)) * 100.0, 2)

    # Dimension 1: Completeness (Weight: 30%)
    s_completeness = max(0.0, 100.0 * (1.0 - (missing_cells / total_cells)))

    # Dimension 2: Uniqueness (Weight: 25%)
    s_uniqueness = max(0.0, 100.0 * (1.0 - (duplicate_rows / max(1, row_count))))

    # Dimension 3: Type Consistency (Weight: 20%)
    s_type_consistency = max(0.0, 100.0 * (1.0 - (total_inconsistent_cells / total_cells)))

    # Dimension 4: Date Validity (Weight: 15%)
    if total_datetime_values > 0:
        s_date_validity = max(0.0, 100.0 * (1.0 - (total_invalid_dates / max(1, total_datetime_values))))
    else:
        s_date_validity = 100.0

    # Dimension 5: Value Reasonableness (Weight: 10%)
    if total_numeric_values > 0:
        s_reasonableness = max(0.0, 100.0 * (1.0 - (total_suspicious_values / max(1, total_numeric_values))))
    else:
        s_reasonableness = 100.0

    # Composite weighted score
    overall = (
        0.30 * s_completeness
        + 0.25 * s_uniqueness
        + 0.20 * s_type_consistency
        + 0.15 * s_date_validity
        + 0.10 * s_reasonableness
    )
    overall_score = float(round(max(0.0, min(100.0, overall)), 1))

    if overall_score >= 90.0:
        grade = "Excellent"
    elif overall_score >= 75.0:
        grade = "Good"
    elif overall_score >= 50.0:
        grade = "Fair"
    else:
        grade = "Poor"

    formula_desc = (
        "0.30*Completeness + 0.25*Uniqueness + 0.20*TypeConsistency + "
        "0.15*DateValidity + 0.10*Reasonableness"
    )

    return DataQualityScore(
        score=overall_score,
        grade=grade,
        formula=formula_desc,
        components=DataQualityComponents(
            completeness=float(round(s_completeness, 1)),
            uniqueness=float(round(s_uniqueness, 1)),
            type_consistency=float(round(s_type_consistency, 1)),
            date_validity=float(round(s_date_validity, 1)),
            reasonableness=float(round(s_reasonableness, 1)),
        ),
        metrics=DataQualityMetrics(
            total_cells=total_cells,
            missing_cells=missing_cells,
            missing_cells_pct=missing_pct,
            duplicate_rows=duplicate_rows,
            duplicate_rows_pct=dup_pct,
            inconsistent_type_cells=total_inconsistent_cells,
            invalid_date_count=total_invalid_dates,
            suspicious_value_count=total_suspicious_values,
        ),
    )


# ---------------------------------------------------------------------------
# Main Public Profiler Entry Point
# ---------------------------------------------------------------------------

def profile_dataframe(df: pd.DataFrame, dataset_id: UUID) -> DatasetProfileResponse:
    """Profile an in-memory DataFrame and return a structured DatasetProfileResponse.

    This function is completely stateless and reusable for:
      - Upload profiling
      - Pre/post cleaning comparisons
      - Ad-hoc analytics dataset summaries
      - AI explanation tools
    """
    row_count = len(df)
    col_count = len(df.columns)
    col_names = [str(c) for c in df.columns]
    memory_size = int(df.memory_usage(deep=True).sum())

    duplicate_rows = int(df.duplicated().sum())
    dup_pct = round((duplicate_rows / max(1, row_count)) * 100.0, 2)
    total_missing = int(df.isna().sum().sum())
    missing_pct = round((total_missing / max(1, row_count * col_count)) * 100.0, 2)

    column_profiles: list[ColumnProfile] = []
    total_inconsistent_cells = 0
    total_invalid_dates = 0
    total_suspicious_values = 0
    total_datetime_values = 0
    total_numeric_values = 0

    for col in df.columns:
        c_prof, inc_cells, inv_dates, susp_vals = profile_column(df[col], str(col))
        column_profiles.append(c_prof)

        total_inconsistent_cells += inc_cells
        total_invalid_dates += inv_dates
        total_suspicious_values += susp_vals

        if c_prof.classification == "datetime":
            total_datetime_values += int(df[col].notna().sum())
        elif c_prof.classification == "numeric":
            total_numeric_values += int(df[col].notna().sum())

    quality_score = calculate_data_quality_score(
        df=df,
        total_inconsistent_cells=total_inconsistent_cells,
        total_invalid_dates=total_invalid_dates,
        total_suspicious_values=total_suspicious_values,
        total_datetime_values=total_datetime_values,
        total_numeric_values=total_numeric_values,
    )

    return DatasetProfileResponse(
        dataset_id=dataset_id,
        row_count=row_count,
        column_count=col_count,
        column_names=col_names,
        memory_size_bytes=memory_size,
        duplicate_row_count=duplicate_rows,
        duplicate_row_percentage=dup_pct,
        total_missing_cells=total_missing,
        missing_cells_percentage=missing_pct,
        columns=column_profiles,
        quality_score=quality_score,
    )


def profile_dataset(file_path: Path | str, file_type: str, dataset_id: UUID) -> DatasetProfileResponse:
    """Load and profile a dataset file from disk."""
    df = load_dataset_dataframe(file_path, file_type)
    return profile_dataframe(df, dataset_id)
