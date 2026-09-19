"use client";

import React, { useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import {
  CleaningConfig,
  CleaningPreviewResponse,
  CleaningReportResponse,
} from "../../lib/types";
import {
  Wand2,
  AlertCircle,
  CheckCircle2,
  Database,
  ArrowRight,
  Eye,
  Sliders,
  ShieldAlert,
  Info,
} from "lucide-react";

export function CleaningView() {
  const { currentDataset, refreshDatasets, setCurrentDataset, setActiveStep } = useAuth();

  const [config, setConfig] = useState<CleaningConfig>({
    remove_duplicates: true,
    numeric_strategy: "median",
    categorical_strategy: "mode",
    normalize_column_names: true,
    normalize_categories: true,
    outlier_handling: "detect_only",
  });

  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<CleaningPreviewResponse | null>(null);

  const [applyLoading, setApplyLoading] = useState(false);
  const [report, setReport] = useState<CleaningReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!currentDataset) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-sm">
        <Database className="h-12 w-12 text-slate-300 mb-3" />
        <h3 className="text-lg font-bold text-slate-900">No Dataset Selected</h3>
        <p className="mt-1 text-sm text-slate-500 max-w-sm">
          Please select or upload a dataset before configuring cleaning rules.
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

  async function handlePreview() {
    setPreviewLoading(true);
    setError(null);
    try {
      const data = await api.previewCleaning(currentDataset!.id, config);
      setPreview(data);
    } catch (err) {
      setError((err as Error).message || "Failed to generate cleaning preview.");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleApply() {
    if (
      !confirm(
        "Apply cleaning transformations? The raw source file remains untouched while a cleaned version is persisted for all analytical and ML stages."
      )
    ) {
      return;
    }

    setApplyLoading(true);
    setError(null);
    try {
      const rep = await api.applyCleaning(currentDataset!.id, config);
      setReport(rep);
      await refreshDatasets();
      // Fetch fresh dataset info
      const updatedDs = await api.getDataset(currentDataset!.id);
      setCurrentDataset(updatedDs);
    } catch (err) {
      setError((err as Error).message || "Failed to apply cleaning.");
    } finally {
      setApplyLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 uppercase tracking-wide">
              Data Cleaning Engine
            </span>
            <span className="text-xs text-slate-400">•</span>
            <span className="text-xs font-medium text-slate-500">
              {currentDataset.name} ({currentDataset.is_cleaned ? "Cleaned" : "Raw"})
            </span>
          </div>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">Cleaning & Standardization</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Configure deduplication, missing value imputation, type normalization, and outlier capping.
          </p>
        </div>

        {currentDataset.is_cleaned && (
          <button
            onClick={() => setActiveStep("analytics")}
            className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700"
          >
            <span>Proceed to Analytics</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold">Operation Error</p>
            <p className="mt-0.5 text-xs text-rose-700">{error}</p>
          </div>
        </div>
      )}

      {/* Applied Report Banner */}
      {report && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-emerald-900 shadow-sm">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="h-6 w-6 text-emerald-600 shrink-0" />
            <div>
              <h3 className="font-bold text-emerald-900">Cleaning Applied Successfully!</h3>
              <p className="text-xs text-emerald-700 mt-0.5">
                Processed dataset is persisted and ready for Analytics, ML, and Root-Cause Analysis.
              </p>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4 text-xs font-medium">
            <div className="rounded-lg bg-white/80 p-3 shadow-sm">
              <span className="text-slate-500">Rows Before:</span>
              <p className="text-base font-bold text-slate-900">{report.rows_before.toLocaleString()}</p>
            </div>
            <div className="rounded-lg bg-white/80 p-3 shadow-sm">
              <span className="text-slate-500">Rows After:</span>
              <p className="text-base font-bold text-slate-900">{report.rows_after.toLocaleString()}</p>
            </div>
            <div className="rounded-lg bg-white/80 p-3 shadow-sm">
              <span className="text-slate-500">Duplicates Removed:</span>
              <p className="text-base font-bold text-emerald-700">{report.duplicates_removed.toLocaleString()}</p>
            </div>
            <div className="rounded-lg bg-white/80 p-3 shadow-sm">
              <span className="text-slate-500">Columns Imputed:</span>
              <p className="text-base font-bold text-indigo-700">
                {Object.keys(report.missing_values_handled).length}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Configuration Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Rules Config Panel */}
        <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-1">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Sliders className="h-4 w-4 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900">Transformation Rules</h3>
          </div>

          {/* Remove Duplicates */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs font-semibold text-slate-800">Deduplication</label>
              <p className="text-[11px] text-slate-500">Remove identical duplicate rows</p>
            </div>
            <input
              type="checkbox"
              checked={config.remove_duplicates}
              onChange={(e) => setConfig({ ...config, remove_duplicates: e.target.checked })}
              className="h-4 w-4 rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer"
            />
          </div>

          {/* Numeric Imputation Strategy */}
          <div>
            <label className="block text-xs font-semibold text-slate-800 mb-1">
              Numeric Missing Strategy
            </label>
            <select
              value={config.numeric_strategy}
              onChange={(e) =>
                setConfig({
                  ...config,
                  numeric_strategy: e.target.value as "median" | "mean" | "zero" | "none",
                })
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-800 focus:border-indigo-600 focus:outline-none"
            >
              <option value="median">Median (robust to outliers)</option>
              <option value="mean">Mean (arithmetic average)</option>
              <option value="zero">Zero (fill 0)</option>
              <option value="none">None (keep nulls)</option>
            </select>
          </div>

          {/* Categorical Imputation Strategy */}
          <div>
            <label className="block text-xs font-semibold text-slate-800 mb-1">
              Categorical Missing Strategy
            </label>
            <select
              value={config.categorical_strategy}
              onChange={(e) =>
                setConfig({
                  ...config,
                  categorical_strategy: e.target.value as "mode" | "unknown" | "none",
                })
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-800 focus:border-indigo-600 focus:outline-none"
            >
              <option value="mode">Mode (most frequent value)</option>
              <option value="unknown">Explicit "Unknown" label</option>
              <option value="none">None (keep nulls)</option>
            </select>
          </div>

          {/* Normalize Headers */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs font-semibold text-slate-800">Snake Case Headers</label>
              <p className="text-[11px] text-slate-500">Normalize column names to lower_snake_case</p>
            </div>
            <input
              type="checkbox"
              checked={config.normalize_column_names}
              onChange={(e) => setConfig({ ...config, normalize_column_names: e.target.checked })}
              className="h-4 w-4 rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer"
            />
          </div>

          {/* Normalize Categories */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs font-semibold text-slate-800">Normalize Categories</label>
              <p className="text-[11px] text-slate-500">Trim whitespace & normalize casing</p>
            </div>
            <input
              type="checkbox"
              checked={config.normalize_categories}
              onChange={(e) => setConfig({ ...config, normalize_categories: e.target.checked })}
              className="h-4 w-4 rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer"
            />
          </div>

          {/* Outlier Handling */}
          <div>
            <label className="block text-xs font-semibold text-slate-800 mb-1">
              Outlier Handling
            </label>
            <select
              value={config.outlier_handling}
              onChange={(e) =>
                setConfig({
                  ...config,
                  outlier_handling: e.target.value as "detect_only" | "cap",
                })
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-800 focus:border-indigo-600 focus:outline-none"
            >
              <option value="detect_only">Detect Only (audit & report)</option>
              <option value="cap">Cap & Floor (winsorize to IQR bounds)</option>
            </select>
          </div>

          {/* Actions */}
          <div className="pt-2 space-y-2">
            <button
              onClick={handlePreview}
              disabled={previewLoading || applyLoading}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-indigo-600 bg-white px-4 py-2.5 text-xs font-semibold text-indigo-600 shadow-sm transition hover:bg-indigo-50 disabled:opacity-50"
            >
              <Eye className="h-4 w-4" />
              <span>{previewLoading ? "Calculating Preview..." : "Preview Transformations"}</span>
            </button>

            <button
              onClick={handleApply}
              disabled={applyLoading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50"
            >
              <Wand2 className="h-4 w-4" />
              <span>{applyLoading ? "Applying Cleaning..." : "Apply & Persist Cleaned Data"}</span>
            </button>
          </div>
        </div>

        {/* Right Preview / Dry Run Output */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-indigo-600" />
              <h3 className="text-sm font-bold text-slate-900">Dry-Run Preview</h3>
            </div>
            {preview && (
              <span className="text-[11px] font-medium text-slate-500">
                Non-destructive simulation
              </span>
            )}
          </div>

          {!preview ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-slate-500">
              <Info className="h-10 w-10 text-slate-300 mb-3" />
              <p className="text-sm font-medium text-slate-700">No Preview Generated Yet</p>
              <p className="text-xs text-slate-400 max-w-sm mt-1">
                Configure your transformation rules on the left and click "Preview Transformations" to inspect row changes, duplicate reductions, and outlier detections without modifying data.
              </p>
            </div>
          ) : (
            <div className="mt-4 space-y-5">
              {/* Overview Metrics */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <span className="text-slate-500">Rows Before:</span>
                  <p className="text-base font-bold text-slate-900 mt-0.5">
                    {preview.rows_before.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <span className="text-slate-500">Rows After (Est):</span>
                  <p className="text-base font-bold text-slate-900 mt-0.5">
                    {preview.rows_after_estimate.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <span className="text-slate-500">Duplicates Detected:</span>
                  <p className="text-base font-bold text-amber-600 mt-0.5">
                    {preview.duplicates_detected.toLocaleString()} ({preview.duplicates_percentage.toFixed(1)}%)
                  </p>
                </div>
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <span className="text-slate-500">Columns to Modify:</span>
                  <p className="text-base font-bold text-indigo-600 mt-0.5">
                    {preview.columns_to_modify.length}
                  </p>
                </div>
              </div>

              {/* Missing Values Handled */}
              {Object.keys(preview.missing_values_detected).length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                    Missing Values Detected by Column
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(preview.missing_values_detected).map(([col, count]) => (
                      <div
                        key={col}
                        className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700"
                      >
                        <span className="font-mono font-medium">{col}: </span>
                        <span className="font-bold text-rose-600">{count} nulls</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Proposed Datatype Changes */}
              {preview.datatype_changes.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                    Proposed Type Casts
                  </h4>
                  <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                    {preview.datatype_changes.map((dt) => (
                      <div key={dt.column} className="flex items-center justify-between p-2.5 text-xs">
                        <span className="font-mono font-semibold text-slate-900">{dt.column}</span>
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-slate-600">
                            {dt.from_type}
                          </span>
                          <span className="text-slate-400">→</span>
                          <span className="rounded bg-indigo-50 px-1.5 py-0.5 font-mono font-semibold text-indigo-700">
                            {dt.to_type}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Outliers Summary */}
              {Object.keys(preview.outlier_summary).length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                    Outlier Summary (IQR Method)
                  </h4>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {Object.entries(preview.outlier_summary).map(([col, out]) => (
                      <div
                        key={col}
                        className="rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-xs"
                      >
                        <div className="flex items-center justify-between font-semibold text-slate-900">
                          <span className="font-mono">{col}</span>
                          <span className="text-amber-700">{out.count} outliers</span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500">
                          Bounds: [{out.lower_bound?.toFixed(1) ?? "—"}, {out.upper_bound?.toFixed(1) ?? "—"}]
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warnings */}
              {preview.warnings.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                  <div className="flex items-center gap-1.5 font-bold mb-1">
                    <ShieldAlert className="h-4 w-4 text-amber-600" />
                    <span>Quality Warnings:</span>
                  </div>
                  <ul className="list-disc pl-4 space-y-0.5 text-[11px]">
                    {preview.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
