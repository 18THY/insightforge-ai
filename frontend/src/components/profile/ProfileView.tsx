"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import { DatasetProfileResponse, ColumnProfile } from "../../lib/types";
import {
  FileCheck2,
  AlertCircle,
  Database,
  Layers,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Wand2,
  TrendingUp,
  Hash,
  Calendar,
  Tag,
  Key,
} from "lucide-react";

export function ProfileView() {
  const { currentDataset, setActiveStep } = useAuth();
  const [profile, setProfile] = useState<DatasetProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedCol, setExpandedCol] = useState<string | null>(null);

  useEffect(() => {
    if (!currentDataset) {
      setProfile(null);
      return;
    }

    async function fetchProfile() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getProfile(currentDataset!.id);
        setProfile(data);
      } catch (err) {
        setError((err as Error).message || "Failed to load dataset profile.");
      } finally {
        setLoading(false);
      }
    }

    fetchProfile();
  }, [currentDataset?.id]);

  if (!currentDataset) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-sm">
        <Database className="h-12 w-12 text-slate-300 mb-3" />
        <h3 className="text-lg font-bold text-slate-900">No Dataset Selected</h3>
        <p className="mt-1 text-sm text-slate-500 max-w-sm">
          Please select or upload a dataset to view its 5-dimensional data quality score and column profiling.
        </p>
        <button
          onClick={() => setActiveStep("dashboard")}
          className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Go to Datasets
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent mb-4" />
        <h3 className="text-base font-semibold text-slate-800">Profiling Dataset...</h3>
        <p className="text-xs text-slate-500 mt-1">Computing null distributions, type inferencing, and quality components</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-rose-800">
        <div className="flex items-center gap-3">
          <AlertCircle className="h-6 w-6 text-rose-600 shrink-0" />
          <div>
            <h3 className="font-bold">Failed to Load Profile</h3>
            <p className="text-xs mt-1 text-rose-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!profile) return null;

  const score = profile.quality_score;
  const gradeColor =
    score.grade === "A"
      ? "text-emerald-700 bg-emerald-100 border-emerald-300"
      : score.grade === "B"
      ? "text-blue-700 bg-blue-100 border-blue-300"
      : score.grade === "C"
      ? "text-amber-700 bg-amber-100 border-amber-300"
      : "text-rose-700 bg-rose-100 border-rose-300";

  function renderClassificationBadge(classification: string) {
    switch (classification) {
      case "identifier":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
            <Key className="h-3 w-3" /> ID
          </span>
        );
      case "categorical":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
            <Tag className="h-3 w-3" /> Categorical
          </span>
        );
      case "numerical_continuous":
      case "numerical_discrete":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
            <Hash className="h-3 w-3" /> Numeric
          </span>
        );
      case "datetime":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
            <Calendar className="h-3 w-3" /> Datetime
          </span>
        );
      default:
        return (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            {classification}
          </span>
        );
    }
  }

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 uppercase tracking-wide">
              Dataset Profile
            </span>
            <span className="text-xs text-slate-400">•</span>
            <span className="text-xs font-medium text-slate-500">
              {profile.row_count.toLocaleString()} rows • {profile.column_count} columns
            </span>
          </div>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">{currentDataset.name}</h1>
          <p className="text-xs text-slate-500 mt-0.5">{currentDataset.original_filename}</p>
        </div>

        <button
          onClick={() => setActiveStep("clean")}
          className="flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
        >
          <Wand2 className="h-4 w-4" />
          <span>Clean & Standardize</span>
        </button>
      </div>

      {/* 5-Dimensional Quality Score Card */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: Score Badge */}
        <div className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                5D Data Quality Score
              </span>
              <Sparkles className="h-4 w-4 text-indigo-600" />
            </div>
            <div className="mt-4 flex items-baseline gap-4">
              <span className="text-5xl font-black tracking-tight text-slate-900">
                {score.score.toFixed(1)}
              </span>
              <span className="text-sm font-medium text-slate-400">/ 100</span>
              <span
                className={`ml-auto rounded-xl border px-3.5 py-1 text-xl font-black ${gradeColor}`}
              >
                Grade {score.grade}
              </span>
            </div>
          </div>

          <div className="mt-6 border-t border-slate-100 pt-4 text-xs text-slate-500">
            <p className="font-semibold text-slate-700 mb-1">Scoring Formula:</p>
            <p className="font-mono text-[11px] leading-relaxed bg-slate-50 p-2 rounded border border-slate-200">
              {score.formula}
            </p>
          </div>
        </div>

        {/* Right: The 5 Components Progress Bars */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
            Quality Component Breakdown
          </h3>

          <div className="space-y-3.5">
            {/* Completeness */}
            <div>
              <div className="flex justify-between text-xs font-medium mb-1">
                <span className="text-slate-700">Completeness (30% weight)</span>
                <span className="font-semibold text-slate-900">
                  {score.components.completeness.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-indigo-600 transition-all"
                  style={{ width: `${score.components.completeness}%` }}
                />
              </div>
            </div>

            {/* Uniqueness */}
            <div>
              <div className="flex justify-between text-xs font-medium mb-1">
                <span className="text-slate-700">Uniqueness (25% weight)</span>
                <span className="font-semibold text-slate-900">
                  {score.components.uniqueness.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-blue-600 transition-all"
                  style={{ width: `${score.components.uniqueness}%` }}
                />
              </div>
            </div>

            {/* Type Consistency */}
            <div>
              <div className="flex justify-between text-xs font-medium mb-1">
                <span className="text-slate-700">Type Consistency (20% weight)</span>
                <span className="font-semibold text-slate-900">
                  {score.components.type_consistency.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-emerald-600 transition-all"
                  style={{ width: `${score.components.type_consistency}%` }}
                />
              </div>
            </div>

            {/* Date Validity */}
            <div>
              <div className="flex justify-between text-xs font-medium mb-1">
                <span className="text-slate-700">Date Validity (15% weight)</span>
                <span className="font-semibold text-slate-900">
                  {score.components.date_validity.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-amber-500 transition-all"
                  style={{ width: `${score.components.date_validity}%` }}
                />
              </div>
            </div>

            {/* Reasonableness */}
            <div>
              <div className="flex justify-between text-xs font-medium mb-1">
                <span className="text-slate-700">Reasonableness (10% weight)</span>
                <span className="font-semibold text-slate-900">
                  {score.components.reasonableness.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-purple-600 transition-all"
                  style={{ width: `${score.components.reasonableness}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Column Schema & Distributions Table */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="border-b border-slate-200 px-6 py-4">
          <h3 className="text-base font-bold text-slate-900">Column Schema & Profiling</h3>
          <p className="text-xs text-slate-500">
            Inferred semantic classifications, missing rates, cardinality, and statistical distributions
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-6 py-3.5">Column Name</th>
                <th className="px-6 py-3.5">Type & Classification</th>
                <th className="px-6 py-3.5">Missing Cells</th>
                <th className="px-6 py-3.5">Unique Values</th>
                <th className="px-6 py-3.5">Sample Values</th>
                <th className="px-6 py-3.5 text-right">Deep Dive</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {profile.columns.map((col) => {
                const isExpanded = expandedCol === col.name;
                return (
                  <React.Fragment key={col.name}>
                    <tr className="hover:bg-slate-50/70 transition">
                      <td className="px-6 py-4 font-mono font-semibold text-slate-900">
                        {col.name}
                      </td>

                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-slate-500">
                            {col.inferred_datatype}
                          </span>
                          {renderClassificationBadge(col.classification)}
                        </div>
                      </td>

                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span
                            className={`font-semibold ${
                              col.null_count > 0 ? "text-amber-600" : "text-emerald-600"
                            }`}
                          >
                            {col.null_count.toLocaleString()}
                          </span>
                          <span className="text-xs text-slate-400">
                            ({col.null_percentage.toFixed(1)}%)
                          </span>
                        </div>
                      </td>

                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-800">
                            {col.unique_count.toLocaleString()}
                          </span>
                          <span className="text-xs text-slate-400">
                            ({col.unique_percentage.toFixed(1)}%)
                          </span>
                        </div>
                      </td>

                      <td className="px-6 py-4">
                        <div className="max-w-[200px] truncate font-mono text-xs text-slate-500">
                          {col.sample_values.slice(0, 3).map((v) => String(v)).join(", ")}
                        </div>
                      </td>

                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => setExpandedCol(isExpanded ? null : col.name)}
                          className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                        >
                          <span>{isExpanded ? "Hide" : "Details"}</span>
                          {isExpanded ? (
                            <ChevronUp className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </td>
                    </tr>

                    {/* Deep Dive Row */}
                    {isExpanded && (
                      <tr className="bg-slate-50/90">
                        <td colSpan={6} className="p-6">
                          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-inner">
                            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
                              Statistical Breakdown: {col.name}
                            </h4>

                            {/* Numeric Stats */}
                            {col.numeric_stats && (
                              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6 text-xs">
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Min:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">{col.numeric_stats.min}</p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Max:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">{col.numeric_stats.max}</p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Mean:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">{col.numeric_stats.mean.toFixed(2)}</p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Median:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">{col.numeric_stats.median.toFixed(2)}</p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Std Dev:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">
                                    {col.numeric_stats.std_dev !== null ? col.numeric_stats.std_dev.toFixed(2) : "—"}
                                  </p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">IQR (P25 - P75):</span>
                                  <p className="font-bold text-slate-900 mt-0.5">
                                    {col.numeric_stats.percentiles["25%"]?.toFixed(1) ?? "—"} -{" "}
                                    {col.numeric_stats.percentiles["75%"]?.toFixed(1) ?? "—"}
                                  </p>
                                </div>
                              </div>
                            )}

                            {/* Categorical Stats */}
                            {col.categorical_stats && (
                              <div>
                                <p className="text-xs text-slate-500 mb-2">
                                  Total unique categories:{" "}
                                  <span className="font-semibold text-slate-800">
                                    {col.categorical_stats.num_categories}
                                  </span>
                                </p>
                                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                                  {col.categorical_stats.top_categories.map((cat) => (
                                    <div
                                      key={cat.value}
                                      className="flex items-center justify-between rounded border border-slate-100 bg-slate-50 px-3 py-2 text-xs"
                                    >
                                      <span className="font-medium text-slate-800 truncate mr-2" title={cat.value}>
                                        {cat.value || "(empty)"}
                                      </span>
                                      <span className="font-mono text-slate-500 shrink-0">
                                        {cat.count.toLocaleString()} ({cat.percentage.toFixed(1)}%)
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Datetime Stats */}
                            {col.datetime_stats && (
                              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-xs">
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Min Date:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">{col.datetime_stats.min_date ?? "—"}</p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Max Date:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">{col.datetime_stats.max_date ?? "—"}</p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Date Range:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">
                                    {col.datetime_stats.date_range_days !== null
                                      ? `${col.datetime_stats.date_range_days} days`
                                      : "—"}
                                  </p>
                                </div>
                                <div className="rounded border border-slate-100 bg-slate-50 p-2.5">
                                  <span className="text-slate-400">Invalid Date Count:</span>
                                  <p className="font-bold text-slate-900 mt-0.5">{col.datetime_stats.invalid_date_count}</p>
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
