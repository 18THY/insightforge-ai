"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import {
  AnomalyItemResponse,
  AnomalyListResponse,
  DatasetProfileResponse,
} from "../../lib/types";
import { ChartWrapper } from "../ChartWrapper";
import {
  AlertTriangle,
  Database,
  ArrowRight,
  ShieldAlert,
  Play,
  Sliders,
  Calendar,
  Layers,
  Sparkles,
  GitMerge,
} from "lucide-react";
import * as echarts from "echarts";

export function AnomaliesView() {
  const { currentDataset, setActiveStep, navigateToRCAWithAnomaly } = useAuth();

  const [profile, setProfile] = useState<DatasetProfileResponse | null>(null);

  const [dateCol, setDateCol] = useState<string>("");
  const [metricCol, setMetricCol] = useState<string>("");
  const [method, setMethod] = useState<"statistical" | "isolation_forest">("statistical");
  const [sensitivity, setSensitivity] = useState<"low" | "medium" | "high">("medium");
  const [cadence, setCadence] = useState<"D" | "W" | "M">("D");
  const [windowSize, setWindowSize] = useState<number>(7);

  const [loading, setLoading] = useState(false);
  const [anomalyResult, setAnomalyResult] = useState<AnomalyListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Discover columns from profile
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
        // Automatically check if anomalies already exist
        api.listAnomalies(currentDataset.id, numCols[0].name).then((res) => {
          if (res && res.anomalies.length > 0) {
            setAnomalyResult(res);
          }
        }).catch(() => {});
      }
    }).catch(console.error);
  }, [currentDataset?.id]);

  async function handleDetect() {
    if (!currentDataset || !dateCol || !metricCol) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.detectAnomalies(currentDataset.id, {
        date_column: dateCol,
        metric_column: metricCol,
        method,
        sensitivity,
        cadence,
        window_size: windowSize,
        persist: true,
      });
      setAnomalyResult(res);
    } catch (err) {
      setError((err as Error).message || "Anomaly detection failed.");
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
          Please select or upload a dataset before running ML anomaly detection.
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

  // --- ECharts Anomaly Plot ---
  const anomalyChartOption: echarts.EChartsOption = {
    tooltip: {
      trigger: "axis",
    },
    grid: { left: "4%", right: "4%", bottom: "10%", top: "12%", containLabel: true },
    xAxis: {
      type: "category",
      data: anomalyResult
        ? anomalyResult.anomalies.map((a) => a.detected_at.split("T")[0])
        : [],
      axisLabel: { color: "#64748b", rotate: 30 },
    },
    yAxis: {
      type: "value",
      name: metricCol,
      splitLine: { lineStyle: { color: "#f1f5f9" } },
    },
    series: [
      {
        name: "Actual Value",
        type: "line",
        smooth: true,
        data: anomalyResult ? anomalyResult.anomalies.map((a) => a.value) : [],
        itemStyle: { color: "#4f46e5" },
        lineStyle: { width: 2 },
      },
      {
        name: "Expected Value",
        type: "line",
        smooth: true,
        data: anomalyResult ? anomalyResult.anomalies.map((a) => a.expected_value) : [],
        itemStyle: { color: "#94a3b8" },
        lineStyle: { type: "dashed", width: 1.5 },
      },
      {
        name: "Detected Anomaly",
        type: "scatter",
        symbolSize: 12,
        data: anomalyResult
          ? anomalyResult.anomalies.map((a, idx) => [idx, a.value])
          : [],
        itemStyle: {
          color: (params: any) => {
            const anom = anomalyResult?.anomalies[params.dataIndex];
            if (anom?.severity === "critical") return "#e11d48";
            if (anom?.severity === "high") return "#ea580c";
            if (anom?.severity === "medium") return "#d97706";
            return "#65a30d";
          },
        },
      },
    ],
  };

  function getSeverityBadge(sev: string) {
    switch (sev) {
      case "critical":
        return (
          <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-bold text-rose-800">
            CRITICAL
          </span>
        );
      case "high":
        return (
          <span className="rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-bold text-orange-800">
            HIGH
          </span>
        );
      case "medium":
        return (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-800">
            MEDIUM
          </span>
        );
      default:
        return (
          <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800">
            LOW
          </span>
        );
    }
  }

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
            <span className="text-xs font-medium text-slate-500">
              {currentDataset.name}
            </span>
          </div>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">Deterministic Anomaly Detection</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Identify statistical outliers using rolling Z-Score windows or scikit-learn IsolationForest algorithms.
          </p>
        </div>

        <button
          onClick={() => setActiveStep("forecasts")}
          className="flex items-center justify-center gap-2 rounded-lg bg-indigo-50 px-4 py-2 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
        >
          <span>Time-Series Forecasts</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertTriangle className="h-5 w-5 shrink-0 text-rose-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold">Detection Error</p>
            <p className="mt-0.5 text-xs text-rose-700">{error}</p>
          </div>
        </div>
      )}

      {/* Controls Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
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
              Algorithm
            </label>
            <select
              value={method}
              onChange={(e) =>
                setMethod(e.target.value as "statistical" | "isolation_forest")
              }
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
            >
              <option value="statistical">Rolling Z-Score</option>
              <option value="isolation_forest">Isolation Forest</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
              Sensitivity
            </label>
            <select
              value={sensitivity}
              onChange={(e) =>
                setSensitivity(e.target.value as "low" | "medium" | "high")
              }
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
            >
              <option value="low">Low (Conservative)</option>
              <option value="medium">Medium (Standard)</option>
              <option value="high">High (Sensitive)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
              Window Size ({windowSize})
            </label>
            <input
              type="range"
              min={3}
              max={30}
              value={windowSize}
              onChange={(e) => setWindowSize(Number(e.target.value))}
              className="w-full cursor-pointer mt-1"
            />
          </div>

          <div className="flex items-end">
            <button
              onClick={handleDetect}
              disabled={loading}
              className="flex w-full items-center justify-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>{loading ? "Scanning..." : "Detect Anomalies"}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Chart Card */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-base font-bold text-slate-900">
            Detected Anomaly Timeline: {metricCol}
          </h3>
          {anomalyResult && (
            <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold text-indigo-700">
              {anomalyResult.total_anomalies} Anomalies Found
            </span>
          )}
        </div>

        {anomalyResult && anomalyResult.anomalies.length > 0 ? (
          <ChartWrapper option={anomalyChartOption} height="360px" loading={loading} />
        ) : (
          <div className="py-20 text-center text-slate-400">
            Configure algorithm parameters above and click "Detect Anomalies" to inspect statistical deviations.
          </div>
        )}
      </div>

      {/* Anomalies Table */}
      {anomalyResult && anomalyResult.anomalies.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-slate-200 px-6 py-4">
            <h3 className="text-base font-bold text-slate-900">Anomalies Audit Log</h3>
            <p className="text-xs text-slate-500">
              Each flagged anomaly can be seamlessly investigated in the Root-Cause Analysis engine with 1 click.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="border-b border-slate-200 bg-slate-50 uppercase text-slate-500 font-semibold">
                <tr>
                  <th className="px-6 py-3.5">Detected Date</th>
                  <th className="px-6 py-3.5">Severity</th>
                  <th className="px-6 py-3.5">Observed Value</th>
                  <th className="px-6 py-3.5">Expected Value</th>
                  <th className="px-6 py-3.5">Deviation %</th>
                  <th className="px-6 py-3.5">Algorithm</th>
                  <th className="px-6 py-3.5 text-right">Root-Cause Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {anomalyResult.anomalies.map((anom, i) => (
                  <tr key={anom.id || i} className="hover:bg-slate-50">
                    <td className="px-6 py-4 font-semibold text-slate-900">
                      {anom.detected_at.split("T")[0]}
                    </td>

                    <td className="px-6 py-4">{getSeverityBadge(anom.severity)}</td>

                    <td className="px-6 py-4 font-mono font-bold text-slate-800">
                      {anom.value !== null ? anom.value.toLocaleString() : "—"}
                    </td>

                    <td className="px-6 py-4 font-mono text-slate-500">
                      {anom.expected_value !== null ? anom.expected_value.toLocaleString() : "—"}
                    </td>

                    <td className="px-6 py-4">
                      <span
                        className={`font-bold ${
                          (anom.deviation_pct ?? 0) >= 0 ? "text-rose-600" : "text-blue-600"
                        }`}
                      >
                        {anom.deviation_pct !== null
                          ? `${anom.deviation_pct > 0 ? "+" : ""}${anom.deviation_pct.toFixed(1)}%`
                          : "—"}
                      </span>
                    </td>

                    <td className="px-6 py-4 text-slate-500">{anom.algorithm || method}</td>

                    <td className="px-6 py-4 text-right">
                      {anom.id ? (
                        <button
                          onClick={() => navigateToRCAWithAnomaly(anom.id!)}
                          className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
                          title="Run Root-Cause Analysis"
                        >
                          <GitMerge className="h-3.5 w-3.5" />
                          <span>Investigate Root Cause</span>
                        </button>
                      ) : (
                        <span className="text-slate-400 italic">Not persisted</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
