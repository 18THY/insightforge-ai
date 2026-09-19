"""services/cleaner.py
===================
Reusable, deterministic data-cleaning engine for InsightForge AI.

Transforms raw datasets according to auditable cleaning rules:
  1. Exact duplicate removal
  2. Missing-value handling with strategy configuration
  3. Column-name normalization with collision safety
  4. Datatype conversion and datetime ISO standardization
  5. Categorical normalization (whitespace and casing harmonization)
  6. Outlier detection (IQR & Z-score) and optional capping
  7. Invalid-value detection
  8. Referential integrity audits on identifier columns
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd

from app.core.storage import get_processed_path, save_processed_file
from app.schemas.cleaning import (
    CleaningConfig,
    CleaningPreviewResponse,
    CleaningReportResponse,
    DatatypeChange,
    OutlierSummary,
    ReferentialSummary,
)
from app.services.profiler import (
    _CONTINUOUS_METRIC_PATTERNS,
    _DATE_NAME_PATTERNS,
    _ID_NAME_PATTERNS,
    load_dataset_dataframe,
    profile_dataframe,
)

# ---------------------------------------------------------------------------
# Column Normalization
# ---------------------------------------------------------------------------

_NORM_CHARS_REGEX = re.compile(r"[^a-z0-9_]+")
_MULTI_UNDERSCORE_REGEX = re.compile(r"_+")


def normalize_column_name(col_name: str) -> str:
    """Normalize a column header to clean snake_case.

    Rules:
      - Strip leading and trailing whitespace
      - Convert to lowercase
      - Replace non-alphanumeric characters with underscores
      - Collapse consecutive underscores
      - Strip leading and trailing underscores
    """
    cleaned = str(col_name).strip().lower()
    cleaned = _NORM_CHARS_REGEX.sub("_", cleaned)
    cleaned = _MULTI_UNDERSCORE_REGEX.sub("_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned if cleaned else "unnamed_col"


def normalize_all_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Normalize all dataframe column names and check for collisions."""
    mapping: dict[str, str] = {}
    used_names: set[str] = set()
    new_cols: list[str] = []

    for c in df.columns:
        original = str(c)
        norm = normalize_column_name(original)
        if norm in used_names:
            raise ValueError(
                f"Column name collision detected: '{original}' and another column both normalize to '{norm}'."
            )
        used_names.add(norm)
        new_cols.append(norm)
        if original != norm:
            mapping[original] = norm

    df_renamed = df.copy()
    df_renamed.columns = new_cols
    return df_renamed, mapping


# ---------------------------------------------------------------------------
# Categorical Normalization
# ---------------------------------------------------------------------------

def normalize_categories(
    series: pd.Series,
) -> tuple[pd.Series, dict[str, str]]:
    """Normalize categorical strings by stripping whitespace and unifying casing.

    Returns:
        tuple: (normalized_series, mapping_of_changes)
    """
    mapping: dict[str, str] = {}
    if series.empty or series.isna().all():
        return series, mapping

    # Strip whitespace
    cleaned = series.astype(str).str.strip()
    non_null_mask = series.notna()

    # Find casing groups
    unique_vals = [v for v in cleaned[non_null_mask].unique() if v and v.lower() != "nan"]
    grouped: dict[str, list[str]] = {}
    for val in unique_vals:
        key = val.lower()
        grouped.setdefault(key, []).append(val)

    # Determine canonical form for groups with multiple casings
    for key, variants in grouped.items():
        if len(variants) > 1:
            # Pick Title Case if available, or most common variant
            title_candidate = key.title()
            canonical = title_candidate if title_candidate in variants else variants[0]
            for v in variants:
                if v != canonical:
                    mapping[v] = canonical

    # Apply mapping
    if mapping:
        res = cleaned.replace(mapping)
        # Restore actual NaNs
        res = res.where(non_null_mask, np.nan)
        return res, mapping

    return cleaned.where(non_null_mask, np.nan), mapping


# ---------------------------------------------------------------------------
# Outlier & Invalid Value Detection
# ---------------------------------------------------------------------------

def detect_outliers_and_invalids(
    series: pd.Series,
    col_name: str,
    classification: str,
    outlier_handling: str = "detect_only",
) -> tuple[pd.Series, int, OutlierSummary | None]:
    """Detect invalid values and numerical outliers (IQR & Z-score)."""
    invalid_count = 0
    outlier_summary = None

    if classification != "numeric":
        return series, invalid_count, outlier_summary

    valid_nums = pd.to_numeric(series, errors="coerce")
    non_null = valid_nums.dropna()

    if len(non_null) == 0:
        return series, invalid_count, outlier_summary

    # Invalid negative checks
    is_positive_metric = bool(_CONTINUOUS_METRIC_PATTERNS.search(str(col_name)))
    if is_positive_metric:
        negatives = non_null < 0
        invalid_count = int(negatives.sum())

    # Outlier detection using IQR (1.5x)
    if len(non_null) >= 10:
        q25 = float(non_null.quantile(0.25))
        q75 = float(non_null.quantile(0.75))
        iqr = q75 - q25
        lower_bound = round(q25 - 1.5 * iqr, 4)
        upper_bound = round(q75 + 1.5 * iqr, 4)

        outlier_mask = (non_null < lower_bound) | (non_null > upper_bound)
        outlier_count = int(outlier_mask.sum())

        sample_outliers = [float(round(x, 4)) for x in non_null[outlier_mask].head(5).tolist()]

        if outlier_count > 0:
            outlier_summary = OutlierSummary(
                column=col_name,
                count=outlier_count,
                method="IQR (1.5x)",
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                sample_outliers=sample_outliers,
            )

            if outlier_handling == "cap":
                series = valid_nums.clip(lower=lower_bound, upper=upper_bound)

    return series, invalid_count, outlier_summary


# ---------------------------------------------------------------------------
# Referential Integrity Checks
# ---------------------------------------------------------------------------

_SUSPICIOUS_ID_PATTERNS = re.compile(r"(9999|unknown|dummy|temp|null|test)", re.IGNORECASE)


def check_referential_column(series: pd.Series, col_name: str) -> ReferentialSummary | None:
    """Check an identifier column for missing references, formatting issues, or placeholder IDs."""
    missing_count = int(series.isna().sum())
    non_null = series.dropna().astype(str)

    invalid_ref_count = 0
    issues: list[str] = []

    if missing_count > 0:
        issues.append(f"{missing_count} missing (null) identifier values found.")

    # Check for placeholder/orphaned pattern IDs like 'PROD9999' or 'UNKNOWN'
    suspicious = [x for x in non_null if _SUSPICIOUS_ID_PATTERNS.search(x)]
    if suspicious:
        invalid_ref_count += len(suspicious)
        distinct_samples = list(set(suspicious))[:3]
        issues.append(
            f"{len(suspicious)} placeholder/suspicious references detected (e.g. {distinct_samples})."
        )

    if missing_count > 0 or invalid_ref_count > 0:
        return ReferentialSummary(
            column=col_name,
            missing_count=missing_count,
            invalid_reference_count=invalid_ref_count,
            issues=issues,
        )

    return None


# ---------------------------------------------------------------------------
# Cleaning Pipeline Core
# ---------------------------------------------------------------------------

def run_cleaning_pipeline(
    df: pd.DataFrame,
    config: CleaningConfig,
    is_preview: bool = True,
) -> tuple[
    pd.DataFrame,
    int,  # rows_before
    int,  # rows_after
    int,  # duplicates_count
    float,  # duplicates_pct
    dict[str, int],  # missing_values_handled
    list[DatatypeChange],
    dict[str, dict[str, str]],  # normalized_categories
    dict[str, int],  # invalid_values
    dict[str, OutlierSummary],
    dict[str, ReferentialSummary],
    list[str],  # warnings
    list[str],  # proposed_actions
]:
    """Execute the core cleaning transformations on a DataFrame copy."""
    df_clean = df.copy()
    rows_before = len(df_clean)
    warnings: list[str] = []
    proposed_actions: list[str] = []

    # 1. Duplicates
    dup_mask = df_clean.duplicated()
    duplicates_count = int(dup_mask.sum())
    duplicates_pct = round((duplicates_count / max(1, rows_before)) * 100.0, 2)

    if duplicates_count > 0:
        proposed_actions.append(f"Remove {duplicates_count} exact duplicate rows ({duplicates_pct}%).")
        if config.remove_duplicates and not is_preview:
            df_clean = df_clean.drop_duplicates(keep="first").reset_index(drop=True)

    rows_after = len(df_clean) if not is_preview else (rows_before - duplicates_count if config.remove_duplicates else rows_before)

    # 2. Column Name Normalization
    col_mapping: dict[str, str] = {}
    if config.normalize_column_names:
        df_clean, col_mapping = normalize_all_columns(df_clean)
        if col_mapping:
            proposed_actions.append(
                f"Normalize {len(col_mapping)} column names to snake_case."
            )

    # Profile DataFrame to inform type-specific operations
    profile_res = profile_dataframe(df_clean, dataset_id=UUID(int=0))
    col_profiles = {c.name: c for c in profile_res.columns}

    # 3. Missing Value Handling
    missing_handled: dict[str, int] = {}
    for col_name, prof in col_profiles.items():
        null_count = int(df_clean[col_name].isna().sum())
        if null_count == 0:
            continue

        if prof.classification == "identifier":
            # CRITICAL RULE: Never fabricate missing IDs
            warnings.append(
                f"Identifier column '{col_name}' has {null_count} missing values. Missing IDs were NOT fabricated."
            )
            continue

        if prof.classification == "datetime":
            # Do not invent dates
            warnings.append(
                f"Datetime column '{col_name}' has {null_count} missing values. Unparseable/missing dates were preserved as null."
            )
            continue

        if prof.classification == "numeric":
            if config.numeric_strategy == "median":
                med_val = df_clean[col_name].median()
                fill_val = 0.0 if pd.isna(med_val) else float(med_val)
                if not is_preview:
                    df_clean[col_name] = df_clean[col_name].fillna(fill_val)
                missing_handled[col_name] = null_count
                proposed_actions.append(f"Impute {null_count} missing values in '{col_name}' with median ({fill_val}).")
            elif config.numeric_strategy == "mean":
                mean_val = df_clean[col_name].mean()
                fill_val = 0.0 if pd.isna(mean_val) else float(round(mean_val, 4))
                if not is_preview:
                    df_clean[col_name] = df_clean[col_name].fillna(fill_val)
                missing_handled[col_name] = null_count
                proposed_actions.append(f"Impute {null_count} missing values in '{col_name}' with mean ({fill_val}).")
            elif config.numeric_strategy == "zero":
                if not is_preview:
                    df_clean[col_name] = df_clean[col_name].fillna(0)
                missing_handled[col_name] = null_count
                proposed_actions.append(f"Fill {null_count} missing values in '{col_name}' with 0.")

        elif prof.classification in ("categorical", "text"):
            if config.categorical_strategy == "mode":
                mode_series = df_clean[col_name].mode(dropna=True)
                fill_val = str(mode_series.iloc[0]) if not mode_series.empty else "Unknown"
                if not is_preview:
                    df_clean[col_name] = df_clean[col_name].fillna(fill_val)
                missing_handled[col_name] = null_count
                proposed_actions.append(f"Impute {null_count} missing values in '{col_name}' with mode ('{fill_val}').")
            elif config.categorical_strategy == "unknown":
                if not is_preview:
                    df_clean[col_name] = df_clean[col_name].fillna("Unknown")
                missing_handled[col_name] = null_count
                proposed_actions.append(f"Fill {null_count} missing values in '{col_name}' with 'Unknown'.")

    # 4. Categorical Normalization
    normalized_categories: dict[str, dict[str, str]] = {}
    if config.normalize_categories:
        for col_name, prof in col_profiles.items():
            if prof.classification == "categorical":
                norm_series, cat_map = normalize_categories(df_clean[col_name])
                if cat_map:
                    normalized_categories[col_name] = cat_map
                    proposed_actions.append(
                        f"Normalize {len(cat_map)} casing variations in '{col_name}'."
                    )
                if not is_preview:
                    df_clean[col_name] = norm_series

    # 5. Datatype Conversions & Datetime Parsing
    datatype_changes: list[DatatypeChange] = []
    for col_name, prof in col_profiles.items():
        orig_dtype = str(df_clean[col_name].dtype)

        if prof.classification == "datetime":
            coerced_dt = pd.to_datetime(df_clean[col_name], errors="coerce", format="mixed")
            success_count = int(coerced_dt.notna().sum())
            fail_count = int(df_clean[col_name].notna().sum() - success_count)
            datatype_changes.append(
                DatatypeChange(
                    column=col_name,
                    from_type=orig_dtype,
                    to_type="datetime (ISO 8601)",
                    success_count=success_count,
                    failure_count=fail_count,
                )
            )
            if not is_preview:
                # Store as clean ISO strings
                df_clean[col_name] = coerced_dt.dt.strftime("%Y-%m-%d").where(coerced_dt.notna(), None)

        elif prof.classification == "numeric" and orig_dtype in ("object", "string"):
            coerced_num = pd.to_numeric(df_clean[col_name], errors="coerce")
            success_count = int(coerced_num.notna().sum())
            fail_count = int(df_clean[col_name].notna().sum() - success_count)
            target_type = prof.inferred_datatype
            datatype_changes.append(
                DatatypeChange(
                    column=col_name,
                    from_type=orig_dtype,
                    to_type=target_type,
                    success_count=success_count,
                    failure_count=fail_count,
                )
            )
            if not is_preview:
                df_clean[col_name] = coerced_num

    # 6. Outliers & Invalid Values
    invalid_values: dict[str, int] = {}
    outliers_detected: dict[str, OutlierSummary] = {}
    for col_name, prof in col_profiles.items():
        ser_out, inv_cnt, out_sum = detect_outliers_and_invalids(
            df_clean[col_name],
            col_name=col_name,
            classification=prof.classification,
            outlier_handling=config.outlier_handling,
        )
        if inv_cnt > 0:
            invalid_values[col_name] = inv_cnt
            warnings.append(f"Column '{col_name}' has {inv_cnt} invalid negative values.")

        if out_sum is not None:
            outliers_detected[col_name] = out_sum
            if config.outlier_handling == "cap":
                proposed_actions.append(f"Cap {out_sum.count} outliers in '{col_name}' using bounds [{out_sum.lower_bound}, {out_sum.upper_bound}].")
            else:
                proposed_actions.append(f"Detected {out_sum.count} outliers in '{col_name}' (reporting only).")

        if not is_preview:
            df_clean[col_name] = ser_out

    # 7. Referential Integrity Checks
    referential_issues: dict[str, ReferentialSummary] = {}
    for col_name, prof in col_profiles.items():
        if prof.classification == "identifier":
            ref_sum = check_referential_column(df_clean[col_name], col_name)
            if ref_sum is not None:
                referential_issues[col_name] = ref_sum

    return (
        df_clean,
        rows_before,
        rows_after,
        duplicates_count,
        duplicates_pct,
        missing_handled,
        datatype_changes,
        normalized_categories,
        invalid_values,
        outliers_detected,
        referential_issues,
        warnings,
        proposed_actions,
    )


# ---------------------------------------------------------------------------
# Public Service API
# ---------------------------------------------------------------------------

def preview_dataset_cleaning(
    file_path: Path | str,
    file_type: str,
    dataset_id: UUID,
    config: CleaningConfig | None = None,
) -> CleaningPreviewResponse:
    """Generate a non-destructive preview of proposed cleaning actions."""
    if config is None:
        config = CleaningConfig()

    df = load_dataset_dataframe(file_path, file_type)

    (
        _,
        rows_before,
        rows_after_est,
        duplicates_count,
        duplicates_pct,
        missing_handled,
        datatype_changes,
        normalized_categories,
        invalid_values,
        outlier_summary,
        referential_issues,
        warnings,
        proposed_actions,
    ) = run_cleaning_pipeline(df, config, is_preview=True)

    # Collect columns to modify
    cols_to_mod = set()
    cols_to_mod.update(missing_handled.keys())
    cols_to_mod.update(c.column for c in datatype_changes)
    cols_to_mod.update(normalized_categories.keys())
    if config.outlier_handling == "cap":
        cols_to_mod.update(outlier_summary.keys())

    # Raw missing values detected for preview
    raw_missing = {str(c): int(df[c].isna().sum()) for c in df.columns if df[c].isna().sum() > 0}

    return CleaningPreviewResponse(
        dataset_id=dataset_id,
        rows_before=rows_before,
        rows_after_estimate=rows_after_est,
        duplicates_detected=duplicates_count,
        duplicates_percentage=duplicates_pct,
        missing_values_detected=raw_missing,
        columns_to_modify=sorted(list(cols_to_mod)),
        datatype_changes=datatype_changes,
        categorical_normalizations=normalized_categories,
        invalid_values=invalid_values,
        outlier_summary=outlier_summary,
        referential_issues=referential_issues,
        warnings=warnings,
        proposed_actions=proposed_actions,
    )


def apply_dataset_cleaning(
    file_path: Path | str,
    file_type: str,
    dataset_id: UUID,
    org_id: UUID,
    config: CleaningConfig | None = None,
) -> tuple[pd.DataFrame, CleaningReportResponse]:
    """Execute cleaning transformations and persist to dedicated processed location."""
    start_time = time.perf_counter()
    if config is None:
        config = CleaningConfig()

    df = load_dataset_dataframe(file_path, file_type)

    (
        cleaned_df,
        rows_before,
        rows_after,
        duplicates_count,
        _,
        missing_handled,
        datatype_changes,
        normalized_categories,
        invalid_values,
        outlier_summary,
        referential_issues,
        warnings,
        _,
    ) = run_cleaning_pipeline(df, config, is_preview=False)

    # Save cleaned dataframe to CSV in processed storage
    csv_bytes = cleaned_df.to_csv(index=False).encode("utf-8")
    saved_path = save_processed_file(csv_bytes, org_id, dataset_id, file_type="csv")

    proc_time_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

    # Safe display path (never expose full absolute system root)
    safe_output_location = f"data/processed/{org_id}/{dataset_id}.csv"

    report = CleaningReportResponse(
        dataset_id=dataset_id,
        rows_before=rows_before,
        rows_after=rows_after,
        duplicates_removed=duplicates_count if config.remove_duplicates else 0,
        missing_values_handled=missing_handled,
        datatype_changes=datatype_changes,
        normalized_categories=normalized_categories,
        invalid_values_found=invalid_values,
        outliers_detected=outlier_summary,
        referential_issues=referential_issues,
        warnings=warnings,
        processing_time_ms=proc_time_ms,
        output_location=safe_output_location,
    )

    return cleaned_df, report
