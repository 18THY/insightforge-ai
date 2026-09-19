"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import { DatasetProfileResponse, ForecastResponse } from "../../lib/types";
import { ChartWrapper } from "../ChartWrapper";
import {
  TrendingUp,
  AlertCircle,
  Database,
  Play,
  Calendar,
  Layers,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import * as echarts from "echarts";

export function ForecastsView() {
  const { currentDataset, setActiveStep } = useAuth();

  const [profile, setProfile] = useState<DatasetProfileResponse | null>(null);

  const [dateCol, setDateCol] = useState<string>("");
  const [metricCol, setMetricCol] = useState<string>("");
  const [cadence, setCadence] = useState<"D" | "W" | "M">("D");
  const [horizonDays, setHorizonDays] = useState<number>(30);
  const [allowNegative, setAllowNegative] = useState<boolean>(false);

  const [loading, setLoading] = useState(false);
  const [forecastResult, setForecastResult] = useState<ForecastResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentDataset) return;
    api.getProfile(currentDataset.id).then((p) => {
      setProfile(p);
      const dateCols = p.columns.filter(
        (c) => c.classification === "datetime" || c.inferred_datatype.includes("date")
      );
      const numCols = p.columns.filter(
        (c) =>
          c.classification === "numerical_continuous" ||
          c.classification === "numerical_discrete" ||
          c.inferred_datatype.includes("float") ||
          c.inferred_datatype.includes("int")
      );

      if (dateCols.length > 0) setDateCol(dateCols[0].name);
      else if (p.columns.length > 0) setDateCol(p.columns[0].name);

      if (numCols.length > 0) {
        setMetricCol(numCols[0].name);
        api.getForecasts(currentDataset.id, numCols[0].name).then((res) => {
          if (res && res.forecasts.length > 0) {
            setForecastResult(res);
          }
        }).catch(() => {});
      }
    }).catch(console.error);
  }, [currentDataset?.id]);

  async function handleForecast() {
    if (!currentDataset || !dateCol || !metricCol) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.generateForecast(currentDataset.id, {
        date_column: dateCol,
        metric_column: metricCol,
        cadence,
        horizon_days: horizonDays,
        allow_negative: allowNegative,
        persist: true,
      });
      setForecastResult(res);
    } catch (err) {
      setError((err as Error).message || "Forecasting failed.");
    } finally {
      setLoading(false);
    }
  }

  if (!currentDataset) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-sm">
        <Database className="h-12 w-12 text-slate-300 mb-3" />
        <h3 className="text-lg font-bold text-slate-900">No Dataset Selected</h3>
        <p className="mt-1 text-sm text-slate-500 max-w-sm">
          Please select or upload a dataset before generating time-series forecasts.
        </p>
        <button
          onClick={() => setActiveStep("dashboard")}
          className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Select Dataset
        </button>
      </div>
    );
  }

  // --- ECharts Forecast with 95% Confidence Band ---
  const forecastChartOption: echarts.EChartsOption = {
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return "";
        const date = params[0].axisValue;
        let html = `<div class="font-semibold text-xs mb-1">${date}</div>`;
        for (const item of params) {
          if (item.seriesName === "Lower Bound Base") continue;
          const val = item.value !== null && item.value !== undefined ? Number(item.value).toLocaleString() : "—";
          html += `<div class="flex items-center justify-between gap-4 text-xs">
            <span style="color:${item.color}">● ${item.seriesName}</span>
            <span class="font-bold font-mono">${val}</span>
          </div>`;
        }
        return html;
      },
    },
    grid: { left: "4%", right: "4%", bottom: "10%", top: "12%", containLabel: true },
    xAxis: {
      type: "category",
      data: forecastResult ? forecastResult.forecasts.map((f) => f.forecast_date) : [],
      axisLabel: { color: "#64748b", rotate: 30 },
    },
    yAxis: {
      type: "value",
      name: `Forecast (${metricCol})`,
      splitLine: { lineStyle: { color: "#f1f5f9" } },
    },
    series: [
      // Base line for confidence band (lower bound)
      {
        name: "Lower Bound Base",
        type: "line",
        data: forecastResult ? forecastResult.forecasts.map((f) => f.lower_bound ?? f.predicted_value) : [],
        lineStyle: { opacity: 0 },
        stack: "confidence-band",
        symbol: "none",
      },
      // Shaded area difference: upper_bound - lower_bound
      {
        name: "95% Prediction Interval",
        type: "line",
        data: forecastResult
          ? forecastResult.forecasts.map((f) =>
              f.upper_bound !== null && f.lower_bound !== null
                ? Math.max(0, f.upper_bound - f.lower_bound)
                : 0
            )
          : [],
        lineStyle: { opacity: 0 },
        areaStyle: { color: "rgba(99, 102, 241, 0.2)" },
        stack: "confidence-band",
        symbol: "none",
      },
      // Predicted line
      {
        name: "Point Forecast",
        type: "line",
        smooth: true,
        data: forecastResult ? forecastResult.forecasts.map((f) => f.predicted_value) : [],
        itemStyle: { color: "#4f46e5" },
        lineStyle: { width: 2.5 },
      },
    ],
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 uppercase tracking-wide">
              ML Engine (Phase 10)
            </span>
            <span className="text-xs text-slate-400">•</span>
            <span className="text-xs font-medium text-slate-500">{currentDataset.name}</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Time-Series Forecasting & 95% Prediction Intervals
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Fit deterministic OLS linear trend + calendar seasonality models with mathematical prediction bands.
          </p>
        </div>

        <button
          onClick={() => setActiveStep("rca")}
          className="flex items-center justify-center gap-2 rounded-lg bg-indigo-50 px-4 py-2 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
        >
          <span>Root-Cause Analysis</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold">Forecasting Error</p>
            <p className="mt-0.5 text-xs text-rose-700">{error}</p>
          </div>
        </div>
      )}

      {/* Controls Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <div>
            <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
              Date Column
            </label>
            <select
              value={dateCol}
              onChange={(e) => setDateCol(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
            >
              {profile?.columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
              Metric Column
            </label>
            <select
              value={metricCol}
              onChange={(e) => setMetricCol(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
            >
              {profile?.columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
              Horizon ({horizonDays} Days)
            </label>
            <select
              value={horizonDays}
              onChange={(e) => setHorizonDays(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
            >
              <option value="7">7 Days Forward</option>
              <option value="14">14 Days Forward</option>
              <option value="30">30 Days Forward</option>
              <option value="60">60 Days Forward</option>
              <option value="90">90 Days Forward</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
              Cadence
            </label>
            <select
              value={cadence}
              onChange={(e) => setCadence(e.target.value as "D" | "W" | "M")}
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
            >
              <option value="D">Daily (D)</option>
              <option value="W">Weekly (W)</option>
              <option value="M">Monthly (M)</option>
            </select>
          </div>

          <div className="flex items-end">
            <button
              onClick={handleForecast}
              disabled={loading}
              className="flex w-full items-center justify-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>{loading ? "Fitting Model..." : "Generate Forecast"}</span>
            </button>
          </div>
        </div>

        <div className="mt-3 flex items-center gap-6 border-t border-slate-100 pt-3 text-xs text-slate-600">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={allowNegative}
              onChange={(e) => setAllowNegative(e.target.checked)}
              className="rounded text-indigo-600"
            />
            <span>Allow Negative Predictions (unconstrained bounds)</span>
          </label>
        </div>
      </div>

      {/* Chart Card */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-base font-bold text-slate-900">
            Forward Forecast Horizon: {metricCol} ({horizonDays} Days)
          </h3>
          {forecastResult && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold text-indigo-700">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {forecastResult.model_name}
            </span>
          )}
        </div>

        {forecastResult && forecastResult.forecasts.length > 0 ? (
          <ChartWrapper option={forecastChartOption} height="400px" loading={loading} />
        ) : (
          <div className="py-20 text-center text-slate-400">
            Configure horizon and click "Generate Forecast" to simulate forward trends and prediction intervals.
          </div>
        )}
      </div>

      {/* Forecast Data Table */}
      {forecastResult && forecastResult.forecasts.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-slate-200 px-6 py-4">
            <h3 className="text-base font-bold text-slate-900">Forecast Schedule & Confidence Intervals</h3>
            <p className="text-xs text-slate-500">
              Point estimates accompanied by 95% mathematical confidence boundaries
            </p>
          </div>

          <div className="overflow-x-auto max-h-[360px]">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="sticky top-0 border-b border-slate-200 bg-slate-50 uppercase text-slate-500 font-semibold">
                <tr>
                  <th className="px-6 py-3">Date</th>
                  <th className="px-6 py-3">Predicted Value</th>
                  <th className="px-6 py-3">Lower 95% Bound</th>
                  <th className="px-6 py-3">Upper 95% Bound</th>
                  <th className="px-6 py-3 text-right">Confidence Spread</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {forecastResult.forecasts.map((pt) => {
                  const spread =
                    pt.upper_bound !== null && pt.lower_bound !== null
                      ? pt.upper_bound - pt.lower_bound
                      : null;
                  return (
                    <tr key={pt.forecast_date} className="hover:bg-slate-50">
                      <td className="px-6 py-3 font-semibold text-slate-900">{pt.forecast_date}</td>

                      <td className="px-6 py-3 font-mono font-bold text-indigo-700">
                        {pt.predicted_value.toLocaleString(undefined, {
                          maximumFractionDigits: 2,
                        })}
                      </td>

                      <td className="px-6 py-3 font-mono text-slate-600">
                        {pt.lower_bound !== null
                          ? pt.lower_bound.toLocaleString(undefined, { maximumFractionDigits: 2 })
                          : "—"}
                      </td>

                      <td className="px-6 py-3 font-mono text-slate-600">
                        {pt.upper_bound !== null
                          ? pt.upper_bound.toLocaleString(undefined, { maximumFractionDigits: 2 })
                          : "—"}
                      </td>

                      <td className="px-6 py-3 font-mono text-right text-slate-500">
                        {spread !== null
                          ? `± ${(spread / 2).toLocaleString(undefined, { maximumFractionDigits: 1 })}`
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
