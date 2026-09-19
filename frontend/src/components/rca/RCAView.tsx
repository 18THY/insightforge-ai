"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import {
  RCAResponse,
  DatasetProfileResponse,
  AnomalyListResponse,
} from "../../lib/types";
import {
  GitMerge,
  AlertCircle,
  Database,
  CheckCircle2,
  AlertTriangle,
  Play,
  Calendar,
  Layers,
  Sparkles,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  Scale,
  FileText,
  ShieldCheck,
} from "lucide-react";

export function RCAView() {
  const { currentDataset, targetAnomalyId, setTargetAnomalyId, setActiveStep } = useAuth();

  const [profile, setProfile] = useState<DatasetProfileResponse | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyListResponse | null>(null);

  // Trigger Mode: "anomaly" | "manual"
  const [triggerMode, setTriggerMode] = useState<"anomaly" | "manual">("anomaly");
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string>("");

  // Manual Trigger Fields
  const [metricCol, setMetricCol] = useState<string>("");
  const [dateCol, setDateCol] = useState<string>("");
  const [aggregation, setAggregation] = useState<"sum" | "avg" | "count">("sum");
  const [eventStart, setEventStart] = useState<string>("");
  const [eventEnd, setEventEnd] = useState<string>("");
  const [baselineMode, setBaselineMode] = useState<"prior_period" | "custom">("prior_period");
  const [baselineStart, setBaselineStart] = useState<string>("");
  const [baselineEnd, setBaselineEnd] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [rcaResult, setRcaResult] = useState<RCAResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load Profile and Anomalies
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
      if (numCols.length > 0) setMetricCol(numCols[0].name);

      // Set default dates if available
      const dtStat = dateCols[0]?.datetime_stats;
      if (dtStat?.min_date && dtStat?.max_date) {
        setEventStart(dtStat.max_date);
        setEventEnd(dtStat.max_date);
      }
    }).catch(console.error);

    api.listAnomalies(currentDataset.id).then((res) => {
      setAnomalies(res);
      if (targetAnomalyId) {
        setSelectedAnomalyId(targetAnomalyId);
        setTriggerMode("anomaly");
      } else if (res.anomalies.length > 0 && res.anomalies[0].id) {
        setSelectedAnomalyId(res.anomalies[0].id);
      }
    }).catch(console.error);
  }, [currentDataset?.id]);

  // If targetAnomalyId was set from AnomaliesView, automatically execute analysis
  useEffect(() => {
    if (targetAnomalyId && currentDataset) {
      setSelectedAnomalyId(targetAnomalyId);
      setTriggerMode("anomaly");
      executeAnomalyRCA(targetAnomalyId);
    }
  }, [targetAnomalyId, currentDataset?.id]);

  async function executeAnomalyRCA(anomalyId: string) {
    if (!currentDataset || !anomalyId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.analyzeAnomalyRCA(currentDataset.id, anomalyId);
      setRcaResult(res);
    } catch (err) {
      setError((err as Error).message || "Automated anomaly RCA failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyze() {
    if (!currentDataset) return;
    setLoading(true);
    setError(null);
    try {
      let res: RCAResponse;
      if (triggerMode === "anomaly") {
        if (!selectedAnomalyId) {
          throw new Error("Please select an anomaly record to analyze.");
        }
        res = await api.analyzeAnomalyRCA(currentDataset.id, selectedAnomalyId);
      } else {
        if (!metricCol || !dateCol || !eventStart || !eventEnd) {
          throw new Error("Metric column, date column, and event start/end dates are required.");
        }
        res = await api.analyzeRCA(currentDataset.id, {
          metric_column: metricCol,
          date_column: dateCol,
          aggregation,
          event_start: eventStart,
          event_end: eventEnd,
          baseline_mode: baselineMode,
          baseline_start: baselineMode === "custom" ? baselineStart || null : null,
          baseline_end: baselineMode === "custom" ? baselineEnd || null : null,
        });
      }
      setRcaResult(res);
    } catch (err) {
      setError((err as Error).message || "Root-cause analysis failed.");
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
          Please select or upload a dataset before performing waterfall root-cause analysis.
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

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 uppercase tracking-wide">
              RCA Engine (Phase 11)
            </span>
            <span className="text-xs text-slate-400">•</span>
            <span className="text-xs font-medium text-slate-500">{currentDataset.name}</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">Waterfall Root-Cause Analysis</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Deterministic driver decomposition, exact statistical z-scores, and 100% waterfall reconciliation.
          </p>
        </div>

        {/* Trigger Mode Toggle */}
        <div className="flex items-center rounded-lg bg-slate-100 p-1 text-xs font-semibold">
          <button
            onClick={() => {
              setTriggerMode("anomaly");
              setTargetAnomalyId(null);
            }}
            className={`rounded-md px-3 py-1.5 transition ${
              triggerMode === "anomaly"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Investigate Anomaly
          </button>
          <button
            onClick={() => {
              setTriggerMode("manual");
              setTargetAnomalyId(null);
            }}
            className={`rounded-md px-3 py-1.5 transition ${
              triggerMode === "manual"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Manual Target & Window
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold">Analysis Error</p>
            <p className="mt-0.5 text-xs text-rose-700">{error}</p>
          </div>
        </div>
      )}

      {/* Trigger Configuration Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        {triggerMode === "anomaly" ? (
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div className="flex-1 max-w-md">
              <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                Select Anomaly Record to Diagnose
              </label>
              <select
                value={selectedAnomalyId}
                onChange={(e) => setSelectedAnomalyId(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:outline-none"
              >
                {anomalies && anomalies.anomalies.length > 0 ? (
                  anomalies.anomalies
                    .filter((a) => a.id)
                    .map((a) => (
                      <option key={a.id} value={a.id!}>
                        {a.detected_at.split("T")[0]} • {a.metric_name} ({a.severity.toUpperCase()},{" "}
                        {a.deviation_pct !== null ? `${a.deviation_pct.toFixed(1)}%` : "—"})
                      </option>
                    ))
                ) : (
                  <option value="">No persisted anomalies available (run Anomaly Detection first)</option>
                )}
              </select>
            </div>

            <button
              onClick={handleAnalyze}
              disabled={loading || !selectedAnomalyId}
              className="flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>{loading ? "Decomposing Drivers..." : "Diagnose Anomaly"}</span>
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
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
                  Aggregation
                </label>
                <select
                  value={aggregation}
                  onChange={(e) => setAggregation(e.target.value as "sum" | "avg" | "count")}
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  <option value="sum">Sum</option>
                  <option value="avg">Average</option>
                  <option value="count">Count</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Event Start Date
                </label>
                <input
                  type="date"
                  value={eventStart}
                  onChange={(e) => setEventStart(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Event End Date
                </label>
                <input
                  type="date"
                  value={eventEnd}
                  onChange={(e) => setEventEnd(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={handleAnalyze}
                disabled={loading}
                className="flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5 fill-current" />
                <span>{loading ? "Running RCA..." : "Execute Root-Cause Analysis"}</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* --- RCA RESULTS PRESENTATION --- */}
      {rcaResult && (
        <div className="space-y-6">
          {/* Executive Narrative Diagnosis Card */}
          <div className="rounded-xl border border-indigo-200 bg-indigo-50/70 p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-indigo-600 p-2 text-white shrink-0 mt-0.5">
                <FileText className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-indigo-900">
                    Automated Root-Cause Diagnosis
                  </h3>
                  <span className="rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-indigo-700 border border-indigo-200">
                    {rcaResult.metric_name} ({rcaResult.aggregation.toUpperCase()})
                  </span>
                </div>
                <p className="mt-2 text-sm text-indigo-950 font-medium leading-relaxed">
                  {rcaResult.narrative_summary}
                </p>
              </div>
            </div>
          </div>

          {/* Waterfall Reconciliation Banner */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col justify-between gap-4 border-b border-slate-100 pb-4 sm:flex-row sm:items-center">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900">
                    Waterfall Decomposition & Reconciliation
                  </h3>
                  {rcaResult.reconciliation.is_reconciled ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-bold text-emerald-700">
                      <CheckCircle2 className="h-3.5 w-3.5" /> 100% Mathematically Reconciled
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-bold text-amber-700">
                      <AlertTriangle className="h-3.5 w-3.5" /> Discrepancy Detected
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Verifies that the sum of pre-truncation segment drivers reconciles to total metric change:{" "}
                  <span className="font-mono font-semibold text-slate-800">
                    ΔY = ∑ Δy_k (tolerance: 0.001)
                  </span>
                </p>
              </div>

              <div className="text-right">
                <span className="text-xs text-slate-400">Total Metric Delta (ΔY):</span>
                <p
                  className={`text-xl font-black ${
                    rcaResult.total_delta >= 0 ? "text-emerald-600" : "text-rose-600"
                  }`}
                >
                  {rcaResult.total_delta > 0 ? "+" : ""}
                  {rcaResult.total_delta.toLocaleString(undefined, { maximumFractionDigits: 2 })} (
                  {rcaResult.percentage_change > 0 ? "+" : ""}
                  {rcaResult.percentage_change.toFixed(1)}%)
                </p>
              </div>
            </div>

            {/* Reconciliation KPI Strip */}
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4 text-xs">
              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-slate-500">Event Window:</span>
                <p className="font-bold text-slate-900 mt-0.5">
                  {rcaResult.event_window.start} → {rcaResult.event_window.end}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-slate-500">Baseline Window:</span>
                <p className="font-bold text-slate-900 mt-0.5">
                  {rcaResult.baseline_window.start} → {rcaResult.baseline_window.end}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-slate-500">Segment Coverage:</span>
                <p className="font-bold text-slate-900 mt-0.5">
                  {rcaResult.reconciliation.truncated_display_count} shown of{" "}
                  {rcaResult.reconciliation.total_segments_count} full segments
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-slate-500">Numerical Discrepancy:</span>
                <p className="font-mono font-bold text-slate-900 mt-0.5">
                  {rcaResult.reconciliation.discrepancy.toFixed(6)}
                </p>
              </div>
            </div>
          </div>

          {/* Primary Ranked Drivers Table */}
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="border-b border-slate-200 px-6 py-4">
              <h3 className="text-base font-bold text-slate-900">Ranked Segment Drivers</h3>
              <p className="text-xs text-slate-500">
                Segment contributions sorted by magnitude with statistical z-score significance:{" "}
                <span className="font-mono">z = (y_event - μ_base) / σ_base</span>
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-600">
                <thead className="border-b border-slate-200 bg-slate-50 uppercase text-slate-500 font-semibold">
                  <tr>
                    <th className="px-6 py-3.5">Segment / Dimension</th>
                    <th className="px-6 py-3.5">Baseline</th>
                    <th className="px-6 py-3.5">Event</th>
                    <th className="px-6 py-3.5">Delta (Δy)</th>
                    <th className="px-6 py-3.5">Contribution %</th>
                    <th className="px-6 py-3.5">Growth %</th>
                    <th className="px-6 py-3.5 text-right">Z-Score Significance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rcaResult.primary_drivers.map((d, idx) => {
                    const isPositive = d.delta >= 0;
                    return (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="px-6 py-4">
                          <div className="font-bold text-slate-900">{d.segment_value}</div>
                          <span className="text-[11px] text-slate-400 font-mono">
                            {d.dimension}
                          </span>
                        </td>

                        <td className="px-6 py-4 font-mono">
                          {d.baseline_value.toLocaleString(undefined, {
                            maximumFractionDigits: 2,
                          })}
                        </td>

                        <td className="px-6 py-4 font-mono font-semibold text-slate-900">
                          {d.event_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>

                        <td className="px-6 py-4 font-mono font-bold">
                          <span className={isPositive ? "text-emerald-600" : "text-rose-600"}>
                            {isPositive ? "+" : ""}
                            {d.delta.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </span>
                        </td>

                        <td className="px-6 py-4 font-semibold">
                          {d.contribution_pct !== null ? (
                            <span>{d.contribution_pct.toFixed(1)}%</span>
                          ) : (
                            <span className="text-slate-400 italic">N/A (ΔY=0)</span>
                          )}
                        </td>

                        <td className="px-6 py-4">
                          <span className={d.growth_pct >= 0 ? "text-emerald-700" : "text-rose-700"}>
                            {d.growth_pct > 0 ? "+" : ""}
                            {d.growth_pct.toFixed(1)}%
                          </span>
                        </td>

                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {d.statistical_score.z_score !== null ? (
                              <span className="font-mono font-semibold text-slate-800">
                                z = {d.statistical_score.z_score > 0 ? "+" : ""}
                                {d.statistical_score.z_score.toFixed(2)}
                              </span>
                            ) : (
                              <span className="font-mono text-slate-400">z = N/A</span>
                            )}
                            {d.statistical_score.is_significant ? (
                              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-800">
                                SIGNIFICANT
                              </span>
                            ) : (
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
                                NORMAL
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Secondary Metric Co-Movement & Elasticity */}
          {rcaResult.secondary_metrics.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
              <div className="border-b border-slate-200 px-6 py-4">
                <h3 className="text-base font-bold text-slate-900">
                  Secondary Metric Co-Movement & Elasticity
                </h3>
                <p className="text-xs text-slate-500">
                  Calculates elasticity coefficient:{" "}
                  <span className="font-mono">ε = (%Δ secondary) / (%Δ target)</span>
                </p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-600">
                  <thead className="border-b border-slate-200 bg-slate-50 uppercase text-slate-500 font-semibold">
                    <tr>
                      <th className="px-6 py-3.5">Metric</th>
                      <th className="px-6 py-3.5">Baseline</th>
                      <th className="px-6 py-3.5">Event</th>
                      <th className="px-6 py-3.5">Shift (Δ)</th>
                      <th className="px-6 py-3.5">Direction</th>
                      <th className="px-6 py-3.5 text-right">Elasticity (ε)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rcaResult.secondary_metrics.map((sec) => (
                      <tr key={sec.metric_name} className="hover:bg-slate-50">
                        <td className="px-6 py-4 font-bold text-slate-900 font-mono">
                          {sec.metric_name}
                        </td>

                        <td className="px-6 py-4 font-mono">
                          {sec.baseline_value.toLocaleString(undefined, {
                            maximumFractionDigits: 2,
                          })}
                        </td>

                        <td className="px-6 py-4 font-mono font-semibold text-slate-900">
                          {sec.event_value.toLocaleString(undefined, {
                            maximumFractionDigits: 2,
                          })}
                        </td>

                        <td className="px-6 py-4 font-mono">
                          <span
                            className={sec.delta >= 0 ? "text-emerald-600" : "text-rose-600"}
                          >
                            {sec.delta > 0 ? "+" : ""}
                            {sec.delta.toLocaleString(undefined, { maximumFractionDigits: 2 })} (
                            {sec.growth_pct > 0 ? "+" : ""}
                            {sec.growth_pct.toFixed(1)}%)
                          </span>
                        </td>

                        <td className="px-6 py-4">
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                              sec.direction === "concordant"
                                ? "bg-indigo-50 text-indigo-700"
                                : sec.direction === "divergent"
                                ? "bg-amber-50 text-amber-700"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {sec.direction}
                          </span>
                        </td>

                        <td className="px-6 py-4 text-right font-mono font-bold text-slate-800">
                          {sec.elasticity !== null ? `ε = ${sec.elasticity.toFixed(2)}` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
