"""services/ml.py
==============
Deterministic Machine Learning and Statistical Intelligence Engine for InsightForge AI.

Implements:
1. Deterministic Time-Series Anomaly Detection:
   - Rolling Z-Score / IQR Statistical Window Detection
   - Fixed-Seed IsolationForest (scikit-learn) with Calibrated Severity Mapping
   - Zero-Variance Handling and Provenance
2. Mathematically Exact Metric Forecasting:
   - Ordinary Least Squares (OLS) Linear Trend with Calendar Seasonality Dummies
   - Exact Prediction Standard Error and Student's t 95% Confidence Intervals
   - Non-Negative Clamping for Intrinsically Non-Negative Business Metrics
   - Degrees of Freedom and Minimum History Validation
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
import scipy.stats
from sklearn.ensemble import IsolationForest

from app.schemas.ml import (
    AnomalyDetectRequest,
    AnomalyItemResponse,
    ForecastGenerateRequest,
    ForecastPointResponse,
)


# ---------------------------------------------------------------------------
# Time-Series Preparation & Semantic Imputation
# ---------------------------------------------------------------------------

def prepare_time_series(
    df: pd.DataFrame,
    date_col: str,
    metric_col: str,
    agg: str = "sum",
    cadence: str = "D",
) -> tuple[pd.Series, dict[str, Any]]:
    """Validate, parse, regularize, and impute a time-series for ML analysis.

    Returns:
        tuple[pd.Series, dict]: Regularized time series and summary metadata.

    Raises:
        ValueError: If columns do not exist, cannot be parsed, or contain no valid data.
    """
    if date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' does not exist in dataset.")
    if metric_col not in df.columns:
        raise ValueError(f"Metric column '{metric_col}' does not exist in dataset.")

    # 1. Parse dates and metrics defensively
    clean_df = pd.DataFrame()
    clean_df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    clean_df["metric"] = pd.to_numeric(df[metric_col], errors="coerce")

    # Drop unparseable dates or metrics
    clean_df = clean_df.dropna(subset=["date", "metric"])
    if len(clean_df) == 0:
        raise ValueError(f"No valid rows found after parsing date '{date_col}' and numeric metric '{metric_col}'.")

    # 2. Resample by cadence
    cadence_map = {
        "D": "D",
        "W": "W-MON",
        "M": "MS",
    }
    freq = cadence_map.get(cadence, "D")

    # Group and aggregate
    grouped = clean_df.set_index("date")["metric"].resample(freq).agg(agg)

    # 3. Missing-value handling within historical boundaries [T_first, T_last]
    # No synthetic zero padding is prepended before start or appended after end.
    if agg in ("sum", "count"):
        # Flow/Volume metrics: missing periods represent 0 activity
        regularized = grouped.fillna(0.0)
    else:
        # Rate/Intensity metrics (mean, median, price): linear interpolation prevents artificial crashes
        regularized = grouped.interpolate(method="linear").bfill().ffill()

    if len(regularized) == 0:
        raise ValueError("Time-series is empty after aggregation and regularization.")

    t_first = regularized.index.min()
    t_last = regularized.index.max()
    now_utc = pd.Timestamp.now(tz=timezone.utc).tz_localize(None)
    lag_days = max(0, (now_utc - t_last).days)

    meta = {
        "start_date": t_first.strftime("%Y-%m-%d"),
        "end_date": t_last.strftime("%Y-%m-%d"),
        "observations_count": len(regularized),
        "cadence": cadence,
        "aggregation": agg,
        "data_recency_lag_days": lag_days,
    }
    return regularized, meta


# ---------------------------------------------------------------------------
# Anomaly Detection Engine
# ---------------------------------------------------------------------------

def detect_anomalies(
    df: pd.DataFrame,
    req: AnomalyDetectRequest,
    dataset_id: UUID,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Execute deterministic anomaly detection over metric time series.

    Returns:
        tuple[list[dict], dict]: List of anomaly dictionaries and provenance metadata.
    """
    ts, prep_meta = prepare_time_series(
        df,
        date_col=req.date_column,
        metric_col=req.metric_column,
        agg=req.aggregation,
        cadence=req.cadence,
    )
    n_obs = len(ts)

    # 1. Enforce minimum observation requirements
    if req.method == "statistical":
        n_min = max(14, 2 * req.window_size)
        if n_obs < n_min:
            raise ValueError(
                f"Insufficient historical data for statistical anomaly detection. "
                f"Found {n_obs} observations, but at least {n_min} are required (window size: {req.window_size})."
            )
    elif req.method == "isolation_forest":
        n_min = 20
        if n_obs < n_min:
            raise ValueError(
                f"Insufficient historical data for Isolation Forest anomaly detection. "
                f"Found {n_obs} observations, but at least {n_min} are required."
            )

    # 2. Zero-variance check
    std_val = float(ts.std())
    mean_val = float(ts.mean())

    if math.isnan(std_val) or std_val < 1e-9:
        provenance = {
            "dataset_id": str(dataset_id),
            "metric_name": req.metric_column,
            "date_column": req.date_column,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "algorithm": req.method,
            "parameters": {
                "method": req.method,
                "sensitivity": req.sensitivity,
                "window_size": req.window_size,
                "cadence": req.cadence,
            },
            "training_period": prep_meta,
            "zero_variance": True,
            "note": "Zero variance detected in historical metric values; no anomalies detected.",
        }
        return [], provenance

    anomalies: list[dict[str, Any]] = []

    # 3. Detection Strategy
    if req.method == "statistical":
        w = req.window_size
        # Use prior window (shifted by 1) so an extreme spike does not inflate its own mean & variance
        prior_ts = ts.shift(1)
        prior_mean = prior_ts.rolling(window=w, min_periods=max(2, w // 2)).mean().bfill()
        prior_std = prior_ts.rolling(window=w, min_periods=max(2, w // 2)).std().fillna(std_val)
        prior_std = np.maximum(prior_std, 1e-4)

        # Standardized residual: z_t = (y_t - mu_t) / sigma_t
        z_scores = (ts - prior_mean) / prior_std

        threshold_map = {
            "low": 3.0,
            "medium": 2.5,
            "high": 2.0,
        }
        z_thresh = threshold_map.get(req.sensitivity, 2.5)

        for dt_idx, val in ts.items():
            z = float(z_scores.loc[dt_idx])
            if math.isnan(z) or abs(z) < z_thresh:
                continue

            v_float = float(round(val, 4))
            exp_val = float(round(prior_mean.loc[dt_idx], 4))
            dev_pct = round(((v_float - exp_val) / max(abs(exp_val), 1e-6)) * 100.0, 2)
            abs_z = abs(z)

            # Severity mapping
            if abs_z >= 4.0 or abs(dev_pct) >= 75.0:
                sev = "critical"
            elif abs_z >= 3.0 or abs(dev_pct) >= 50.0:
                sev = "high"
            elif abs_z >= 2.5 or abs(dev_pct) >= 25.0:
                sev = "medium"
            else:
                sev = "low"

            desc = (
                f"Statistical anomaly: Value {v_float} deviated by {dev_pct}% "
                f"from {w}-period rolling expected {exp_val} (z-score: {round(z, 2)})."
            )

            anomalies.append({
                "metric_name": req.metric_column,
                "detected_at": dt_idx.to_pydatetime().replace(tzinfo=timezone.utc),
                "severity": sev,
                "value": v_float,
                "expected_value": exp_val,
                "deviation_pct": dev_pct,
                "description": desc,
                "algorithm": "rolling_zscore",
            })

    elif req.method == "isolation_forest":
        contamination_map = {
            "low": 0.01,
            "medium": 0.03,
            "high": 0.05,
        }
        contam = contamination_map.get(req.sensitivity, 0.03)

        # Feature matrix: [metric_value, time_trend_index]
        X = np.column_stack([ts.values, np.arange(len(ts), dtype=float)])

        # Deterministic fixed seed
        iso = IsolationForest(
            contamination=contam,
            random_state=42,
            n_estimators=100,
        )
        iso.fit(X)

        decision_vals = iso.decision_function(X)
        # Normalized anomaly score: higher = more anomalous; >= 0 indicates outlier
        anomaly_scores = -decision_vals

        median_val = float(ts.median())

        for idx, (dt_idx, val) in enumerate(ts.items()):
            score = float(anomaly_scores[idx])
            if score <= 0.0:
                continue

            v_float = float(round(val, 4))
            exp_val = float(round(median_val, 4))
            dev_pct = round(((v_float - exp_val) / max(abs(exp_val), 1e-6)) * 100.0, 2)
            z_mag = abs(v_float - mean_val) / max(std_val, 1e-6)

            # Calibrated deterministic severity mapping
            if score >= 0.15 or z_mag >= 4.0:
                sev = "critical"
            elif score >= 0.10 or z_mag >= 3.0:
                sev = "high"
            elif score >= 0.05 or z_mag >= 2.5:
                sev = "medium"
            else:
                sev = "low"

            desc = (
                f"IsolationForest outlier (score: {round(score, 4)}): "
                f"Observed {v_float} vs baseline median {exp_val} (deviation: {dev_pct}%, z-mag: {round(z_mag, 2)})."
            )

            anomalies.append({
                "metric_name": req.metric_column,
                "detected_at": dt_idx.to_pydatetime().replace(tzinfo=timezone.utc),
                "severity": sev,
                "value": v_float,
                "expected_value": exp_val,
                "deviation_pct": dev_pct,
                "description": desc,
                "algorithm": "isolation_forest",
            })

    provenance = {
        "dataset_id": str(dataset_id),
        "metric_name": req.metric_column,
        "date_column": req.date_column,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": req.method,
        "parameters": {
            "method": req.method,
            "sensitivity": req.sensitivity,
            "window_size": req.window_size if req.method == "statistical" else None,
            "random_state": 42 if req.method == "isolation_forest" else None,
            "cadence": req.cadence,
        },
        "training_period": prep_meta,
        "total_anomalies_detected": len(anomalies),
    }

    return anomalies, provenance


# ---------------------------------------------------------------------------
# Time-Series Forecasting Engine (Ordinary Least Squares)
# ---------------------------------------------------------------------------

def generate_forecast(
    df: pd.DataFrame,
    req: ForecastGenerateRequest,
    dataset_id: UUID,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fit OLS linear trend + calendar seasonality model and generate 95% prediction intervals.

    Returns:
        tuple[list[dict], dict]: List of forecast point dictionaries and provenance metadata.

    Raises:
        ValueError: If data is insufficient for requested horizon or degrees of freedom N <= p.
    """
    ts, prep_meta = prepare_time_series(
        df,
        date_col=req.date_column,
        metric_col=req.metric_column,
        agg=req.aggregation,
        cadence=req.cadence,
    )
    n_obs = len(ts)
    h_steps = req.horizon_days

    # 1. Enforce minimum observations: N >= max(14, 2 * H)
    n_min = max(14, 2 * h_steps)
    if n_obs < n_min:
        raise ValueError(
            f"Insufficient historical data for a {h_steps}-day forecast. "
            f"Found {n_obs} observations, but at least {n_min} observations are required."
        )

    # 2. Determine seasonal period m and dynamic parameter count p
    cadence_period_map = {
        "D": 7,    # Day of week
        "M": 12,   # Month of year
        "W": 52,   # Week of year
    }
    m = cadence_period_map.get(req.cadence, 7)

    # Check if seasonality can be verified (requires >= 2 full seasonal cycles)
    if n_obs >= 2 * m:
        seasonality_applied = True
        p = m + 1  # Intercept (1) + trend (1) + (m - 1) dummy variables = m + 1
    else:
        seasonality_applied = False
        p = 2  # Intercept (1) + trend (1)

    # 3. Model validity & degrees of freedom check: N must be strictly greater than p
    if n_obs <= p:
        raise ValueError(
            f"Insufficient degrees of freedom for model fitting. "
            f"Dataset contains N={n_obs} observations, but model requires p={p} parameters (N must be greater than p)."
        )

    df_resid = n_obs - p

    # 4. Construct Design Matrix X (N x p)
    y = ts.values.astype(float)
    X = np.zeros((n_obs, p), dtype=float)

    # Column 0: Intercept
    X[:, 0] = 1.0
    # Column 1: Linear time trend t = 1 ... N
    X[:, 1] = np.arange(1, n_obs + 1, dtype=float)

    # Seasonal dummy columns
    if seasonality_applied:
        if req.cadence == "D":
            cycle_indices = ts.index.dayofweek.values  # 0 to 6
        elif req.cadence == "M":
            cycle_indices = ts.index.month.values - 1  # 0 to 11
        elif req.cadence == "W":
            cycle_indices = (ts.index.isocalendar().week.values - 1) % 52  # 0 to 51
        else:
            cycle_indices = np.zeros(n_obs, dtype=int)

        # Populate m-1 dummy columns (period 0 is the omitted reference category)
        for col_idx in range(1, m):
            X[:, 1 + col_idx] = (cycle_indices == col_idx).astype(float)

    # 5. OLS Parameter Estimation via Normal Equations
    # Beta = (X^T X)^(-1) X^T y
    XtX = X.T @ X
    # Numerical inversion using pinv / solve
    try:
        XtX_inv = np.linalg.inv(XtX)
        beta = XtX_inv @ (X.T @ y)
    except np.linalg.LinAlgError:
        XtX_inv = np.linalg.pinv(XtX)
        beta = XtX_inv @ (X.T @ y)

    # In-sample fitted values and residuals
    y_hat = X @ beta
    residuals = y - y_hat
    sse = float(np.sum(residuals ** 2))

    # Residual Standard Error: s = sqrt(SSE / (N - p))
    rse = math.sqrt(max(1e-12, sse / df_resid))

    # Critical Student's t value for two-tailed 95% confidence (alpha = 0.05, 0.975 quantile)
    t_crit = float(scipy.stats.t.ppf(0.975, df=df_resid))

    # 6. Generate Forecast Points for Horizon
    t_last = ts.index[-1]
    if req.cadence == "D":
        future_dates = pd.date_range(start=t_last + pd.Timedelta(days=1), periods=h_steps, freq="D")
    elif req.cadence == "W":
        future_dates = pd.date_range(start=t_last + pd.Timedelta(weeks=1), periods=h_steps, freq="W-MON")
    elif req.cadence == "M":
        future_dates = pd.date_range(start=t_last + pd.DateOffset(months=1), periods=h_steps, freq="MS")
    else:
        future_dates = pd.date_range(start=t_last + pd.Timedelta(days=1), periods=h_steps, freq="D")

    forecast_points: list[dict[str, Any]] = []
    y_min_hist = float(np.min(y))
    model_label = "OLSSeasonalTrend" if seasonality_applied else "OLSTrend"

    for h_idx, f_dt in enumerate(future_dates, start=1):
        x_future = np.zeros(p, dtype=float)
        x_future[0] = 1.0
        x_future[1] = float(n_obs + h_idx)

        if seasonality_applied:
            if req.cadence == "D":
                c_idx = f_dt.dayofweek
            elif req.cadence == "M":
                c_idx = f_dt.month - 1
            elif req.cadence == "W":
                c_idx = (f_dt.isocalendar().week - 1) % 52
            else:
                c_idx = 0

            if 1 <= c_idx < m:
                x_future[1 + c_idx] = 1.0

        # Point forecast: y_hat = x_future^T Beta
        pred_val = float(x_future @ beta)

        # Prediction Standard Error: SE_pred = s * sqrt(1 + x_future^T (X^T X)^(-1) x_future)
        leverage = float(x_future @ (XtX_inv @ x_future))
        se_pred = rse * math.sqrt(max(1.0, 1.0 + leverage))

        margin = t_crit * se_pred
        upper_b = round(pred_val + margin, 4)
        lower_b = round(pred_val - margin, 4)

        # Lower bound clamping logic:
        # Clamped only if allow_negative is False, historical minimum >= 0, and aggregation is sum or count
        if not req.allow_negative and y_min_hist >= 0.0 and req.aggregation in ("sum", "count"):
            lower_b = max(0.0, lower_b)

        forecast_points.append({
            "forecast_date": f_dt.date(),
            "predicted_value": round(pred_val, 4),
            "lower_bound": lower_b,
            "upper_bound": upper_b,
            "model_name": model_label,
        })

    provenance = {
        "dataset_id": str(dataset_id),
        "metric_name": req.metric_column,
        "date_column": req.date_column,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": model_label,
        "algorithm": "ordinary_least_squares_linear_trend" + ("_with_calendar_seasonality" if seasonality_applied else ""),
        "parameters": {
            "cadence": req.cadence,
            "horizon_days": req.horizon_days,
            "seasonal_period": m if seasonality_applied else None,
            "parameters_count": p,
            "degrees_of_freedom": df_resid,
            "seasonality_applied": seasonality_applied,
            "fallback_reason": None if seasonality_applied else "Insufficient historical cycles for seasonal decomposition (requires at least 2 full cycles).",
        },
        "training_period": prep_meta,
        "residual_standard_error": round(rse, 4),
        "sum_squared_errors": round(sse, 4),
        "confidence_level": 0.95,
        "t_critical": round(t_crit, 4),
    }

    return forecast_points, provenance
