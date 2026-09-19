"use client";

import React, { useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import { DatasetResponse } from "../../lib/types";
import {
  Database,
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  Trash2,
  FileCheck2,
  BarChart3,
  Calendar,
  Layers,
  ArrowUpRight,
  Sparkles,
  RefreshCw,
  TrendingUp,
  BrainCircuit,
  ShieldCheck,
} from "lucide-react";

export function DashboardView() {
  const {
    currentOrg,
    datasets,
    currentDataset,
    setCurrentDataset,
    refreshDatasets,
    setActiveStep,
  } = useAuth();

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const totalDatasets = datasets.length;
  const cleanedDatasets = datasets.filter((d) => d.is_cleaned).length;
  const totalRows = datasets.reduce((acc, d) => acc + (d.row_count || 0), 0);

  const pipelineProgress =
    totalDatasets > 0
      ? Math.round((cleanedDatasets / totalDatasets) * 100)
      : 0;

  function formatBytes(bytes: number): string {
    if (!bytes || bytes === 0) return "0 B";

    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return (
      parseFloat((bytes / Math.pow(k, i)).toFixed(1)) +
      " " +
      sizes[i]
    );
  }

  async function handleDelete(dataset: DatasetResponse) {
    if (
      !confirm(
        `Are you sure you want to delete dataset "${dataset.name}"?`
      )
    ) {
      return;
    }

    setDeletingId(dataset.id);

    try {
      await api.deleteDataset(dataset.id);

      if (currentDataset?.id === dataset.id) {
        setCurrentDataset(null);
      }

      await refreshDatasets();
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);

    try {
      await refreshDatasets();
    } finally {
      setTimeout(() => setRefreshing(false), 500);
    }
  }

  function handleSelectAndOpen(
    dataset: DatasetResponse,
    step: "profile" | "analytics"
  ) {
    setCurrentDataset(dataset);
    setActiveStep(step);
  }

  return (
    <div className="animate-fade-in min-h-full space-y-7 bg-slate-50/60 pb-10">

      {/* ===================================================== */}
      {/* PREMIUM HERO */}
      {/* ===================================================== */}
      <section className="hero-grid relative overflow-hidden rounded-[28px] border border-indigo-400/10 bg-gradient-to-br from-slate-950 via-indigo-950 to-violet-950 p-7 text-white shadow-2xl shadow-indigo-950/10 sm:p-8 lg:p-9">

        {/* Background glow */}
        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 left-1/3 h-72 w-72 rounded-full bg-violet-500/20 blur-3xl" />

        <div className="relative grid gap-8 lg:grid-cols-[1fr_360px] lg:items-center">

          {/* Left */}
          <div>
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-indigo-200 backdrop-blur-md">
              <Sparkles className="h-3.5 w-3.5 text-indigo-300" />
              <span>{currentOrg?.name || "Workspace"}</span>
              <span className="text-slate-500">•</span>
              <span>AI Analytics Platform</span>
            </div>

            <h1 className="max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
              Turn your data into
              <span className="ml-2 bg-gradient-to-r from-indigo-300 via-violet-300 to-white bg-clip-text text-transparent">
                insights.
              </span>
            </h1>

            <p className="mt-4 max-w-xl text-sm leading-6 text-slate-300 sm:text-base">
              Upload business data, understand its quality, discover hidden
              patterns, detect anomalies, forecast trends, and investigate
              root causes from one workspace.
            </p>

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                onClick={() => setActiveStep("upload")}
                className="group inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-900 shadow-xl shadow-black/20 transition-all duration-200 hover:-translate-y-0.5 hover:bg-indigo-50"
              >
                <UploadCloud className="h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
                Upload Dataset
                <ArrowUpRight className="h-4 w-4" />
              </button>

              {currentDataset && (
                <button
                  onClick={() =>
                    handleSelectAndOpen(currentDataset, "analytics")
                  }
                  className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white backdrop-blur-md transition hover:bg-white/10"
                >
                  <BarChart3 className="h-4 w-4" />
                  Open Analytics
                </button>
              )}
            </div>
          </div>

          {/* Right visual */}
          <div className="ai-glow relative rounded-2xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur-xl">

            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-400">
                  InsightForge AI
                </p>

                <p className="mt-1 text-sm font-semibold text-white">
                  Workspace Intelligence
                </p>
              </div>

              <div className="rounded-xl bg-indigo-500/15 p-2.5 text-indigo-300">
                <BrainCircuit className="h-5 w-5" />
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-white/10 bg-black/10 p-3">
                <div className="flex items-center gap-2 text-slate-400">
                  <TrendingUp className="h-3.5 w-3.5" />
                  <span className="text-[11px]">Datasets</span>
                </div>

                <p className="mt-2 text-2xl font-bold text-white">
                  {totalDatasets}
                </p>
              </div>

              <div className="rounded-xl border border-white/10 bg-black/10 p-3">
                <div className="flex items-center gap-2 text-slate-400">
                  <Layers className="h-3.5 w-3.5" />
                  <span className="text-[11px]">Rows</span>
                </div>

                <p className="mt-2 text-2xl font-bold text-white">
                  {totalRows.toLocaleString()}
                </p>
              </div>

              <div className="rounded-xl border border-white/10 bg-black/10 p-3">
                <div className="flex items-center gap-2 text-slate-400">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  <span className="text-[11px]">Cleaned</span>
                </div>

                <p className="mt-2 text-2xl font-bold text-emerald-300">
                  {pipelineProgress}%
                </p>
              </div>

              <div className="rounded-xl border border-white/10 bg-black/10 p-3">
                <div className="flex items-center gap-2 text-slate-400">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span className="text-[11px]">AI Ready</span>
                </div>

                <p className="mt-2 text-2xl font-bold text-indigo-300">
                  {currentDataset ? "YES" : "—"}
                </p>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-2 rounded-xl border border-emerald-400/10 bg-emerald-400/5 px-3 py-2.5">
              <span className="status-dot status-dot-success" />

              <span className="text-[11px] font-medium text-emerald-200">
                Analytics pipeline ready
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ===================================================== */}
      {/* KPI CARDS */}
      {/* ===================================================== */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">

        {/* Card 1 */}
        <div className="premium-card group p-5 animate-slide-up">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Total Datasets
              </p>

              <p className="mt-3 text-3xl font-bold tracking-tight text-slate-950">
                {totalDatasets}
              </p>

              <p className="mt-1 text-xs text-slate-500">
                Active in this workspace
              </p>
            </div>

            <div className="rounded-xl bg-indigo-50 p-3 text-indigo-600 transition duration-200 group-hover:scale-110 group-hover:bg-indigo-100">
              <Database className="h-5 w-5" />
            </div>
          </div>

          <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-700"
              style={{ width: totalDatasets > 0 ? "100%" : "0%" }}
            />
          </div>
        </div>

        {/* Card 2 */}
        <div className="premium-card group p-5 animate-slide-up">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Cleaned Datasets
              </p>

              <p className="mt-3 text-3xl font-bold tracking-tight text-slate-950">
                {cleanedDatasets}
              </p>

              <p className="mt-1 text-xs text-slate-500">
                {totalDatasets > 0
                  ? `${pipelineProgress}% pipeline ready`
                  : "No datasets yet"}
              </p>
            </div>

            <div className="rounded-xl bg-emerald-50 p-3 text-emerald-600 transition duration-200 group-hover:scale-110 group-hover:bg-emerald-100">
              <CheckCircle2 className="h-5 w-5" />
            </div>
          </div>

          <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-all duration-700"
              style={{ width: `${pipelineProgress}%` }}
            />
          </div>
        </div>

        {/* Card 3 */}
        <div className="premium-card group p-5 animate-slide-up">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Ingested Rows
              </p>

              <p className="mt-3 text-3xl font-bold tracking-tight text-slate-950">
                {totalRows.toLocaleString()}
              </p>

              <p className="mt-1 text-xs text-slate-500">
                Across all datasets
              </p>
            </div>

            <div className="rounded-xl bg-blue-50 p-3 text-blue-600 transition duration-200 group-hover:scale-110 group-hover:bg-blue-100">
              <Layers className="h-5 w-5" />
            </div>
          </div>

          <div className="mt-5 flex items-center gap-2 text-xs font-medium text-blue-600">
            <TrendingUp className="h-3.5 w-3.5" />
            Data volume tracked
          </div>
        </div>

        {/* Card 4 */}
        <div className="premium-card group p-5 animate-slide-up">
          <div className="flex items-start justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Active Dataset
              </p>

              <p
                className="mt-3 truncate text-xl font-bold tracking-tight text-slate-950"
                title={currentDataset?.name || "None"}
              >
                {currentDataset?.name || "None Selected"}
              </p>

              <p className="mt-1 text-xs text-slate-500">
                {currentDataset
                  ? `${currentDataset.row_count?.toLocaleString() || 0} rows • ${
                      currentDataset.file_type?.toUpperCase() ?? ""
                    }`
                  : "Select a dataset to begin"}
              </p>
            </div>

            <div className="ml-3 rounded-xl bg-amber-50 p-3 text-amber-600 transition duration-200 group-hover:scale-110 group-hover:bg-amber-100">
              <BarChart3 className="h-5 w-5" />
            </div>
          </div>

          {currentDataset && (
            <button
              onClick={() =>
                handleSelectAndOpen(currentDataset, "analytics")
              }
              className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 transition hover:text-indigo-700"
            >
              Open analytics
              <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </section>

      {/* ===================================================== */}
      {/* MAIN CONTENT */}
      {/* ===================================================== */}
      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_320px]">

        {/* Dataset catalog */}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div>
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600">
                  <Database className="h-4 w-4" />
                </div>

                <h2 className="text-base font-bold text-slate-950">
                  Dataset Catalog
                </h2>
              </div>

              <p className="mt-2 text-xs leading-5 text-slate-500">
                Browse, profile, analyze, and manage your uploaded business
                datasets.
              </p>
            </div>

            <button
              onClick={handleRefresh}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${
                  refreshing ? "animate-spin" : ""
                }`}
              />
              Refresh
            </button>
          </div>

          {datasets.length === 0 ? (
            <div className="flex min-h-[340px] flex-col items-center justify-center px-6 py-12 text-center">
              <div className="animate-float mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-50 to-violet-50 text-indigo-600 ring-8 ring-indigo-50/60">
                <UploadCloud className="h-7 w-7" />
              </div>

              <h3 className="text-lg font-bold text-slate-950">
                Your workspace is empty
              </h3>

              <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
                Upload a CSV or XLSX business dataset to start profiling,
                cleaning, analyzing, forecasting, and discovering insights.
              </p>

              <button
                onClick={() => setActiveStep("upload")}
                className="mt-6 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-600/20 transition hover:bg-indigo-700 hover:shadow-xl"
              >
                <UploadCloud className="h-4 w-4" />
                Upload Your First Dataset
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left">
                <thead className="border-b border-slate-200 bg-slate-50/80">
                  <tr className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    <th className="px-6 py-4">Dataset</th>
                    <th className="px-6 py-4">Status</th>
                    <th className="px-6 py-4">Rows / Columns</th>
                    <th className="px-6 py-4">Size</th>
                    <th className="px-6 py-4">Uploaded</th>
                    <th className="px-6 py-4 text-right">Actions</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100">
                  {datasets.map((dataset) => {
                    const isCurrent = currentDataset?.id === dataset.id;

                    return (
                      <tr
                        key={dataset.id}
                        className={`group transition ${
                          isCurrent
                            ? "bg-indigo-50/60"
                            : "hover:bg-slate-50/70"
                        }`}
                      >
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <div
                              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                                dataset.is_cleaned
                                  ? "bg-emerald-50 text-emerald-600"
                                  : "bg-indigo-50 text-indigo-600"
                              }`}
                            >
                              <Database className="h-4 w-4" />
                            </div>

                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="max-w-[220px] truncate text-sm font-semibold text-slate-900">
                                  {dataset.name}
                                </span>

                                {isCurrent && (
                                  <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[9px] font-bold tracking-wider text-indigo-700">
                                    ACTIVE
                                  </span>
                                )}
                              </div>

                              <span className="mt-0.5 block max-w-[240px] truncate text-xs text-slate-400">
                                {dataset.original_filename}
                              </span>
                            </div>
                          </div>
                        </td>

                        <td className="px-6 py-4">
                          {dataset.is_cleaned ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Cleaned
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
                              <AlertCircle className="h-3.5 w-3.5" />
                              Raw
                            </span>
                          )}
                        </td>

                        <td className="px-6 py-4">
                          <div className="text-sm font-semibold text-slate-800">
                            {dataset.row_count !== null
                              ? dataset.row_count.toLocaleString()
                              : "—"}{" "}
                            <span className="font-normal text-slate-400">
                              rows
                            </span>
                          </div>

                          <div className="mt-1 text-xs text-slate-400">
                            {dataset.column_count ?? "—"} columns
                          </div>
                        </td>

                        <td className="px-6 py-4 text-sm font-medium text-slate-700">
                          {formatBytes(dataset.file_size_bytes)}
                        </td>

                        <td className="px-6 py-4">
                          <div className="flex items-center gap-1.5 text-xs text-slate-500">
                            <Calendar className="h-3.5 w-3.5" />
                            {new Date(
                              dataset.created_at
                            ).toLocaleDateString()}
                          </div>
                        </td>

                        <td className="px-6 py-4">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() =>
                                handleSelectAndOpen(dataset, "profile")
                              }
                              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700"
                            >
                              <FileCheck2 className="h-3.5 w-3.5" />
                              Profile
                            </button>

                            <button
                              onClick={() =>
                                handleSelectAndOpen(dataset, "analytics")
                              }
                              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-sm shadow-indigo-600/20 transition hover:bg-indigo-700 hover:shadow-md"
                            >
                              <BarChart3 className="h-3.5 w-3.5" />
                              Analyze
                              <ArrowUpRight className="h-3 w-3" />
                            </button>

                            <button
                              disabled={deletingId === dataset.id}
                              onClick={() => handleDelete(dataset)}
                              className="rounded-lg p-2 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
                              title="Delete dataset"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pipeline */}
        <aside className="premium-card p-5">
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-violet-50 p-2 text-violet-600">
              <Sparkles className="h-4 w-4" />
            </div>

            <h3 className="text-sm font-bold text-slate-950">
              InsightForge Pipeline
            </h3>
          </div>

          <p className="mt-2 text-xs leading-5 text-slate-500">
            Your data moves through the analytics workflow step by step.
          </p>

          <div className="mt-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-50 text-xs font-bold text-indigo-600">
                1
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-800">
                  Upload
                </p>

                <p className="text-[11px] text-slate-400">
                  Ingest your dataset
                </p>
              </div>
            </div>

            <div className="ml-4 h-5 w-px bg-slate-200" />

            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-xs font-bold text-emerald-600">
                2
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-800">
                  Profile & Clean
                </p>

                <p className="text-[11px] text-slate-400">
                  Understand data quality
                </p>
              </div>
            </div>

            <div className="ml-4 h-5 w-px bg-slate-200" />

            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-50 text-xs font-bold text-blue-600">
                3
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-800">
                  Analyze
                </p>

                <p className="text-[11px] text-slate-400">
                  Explore charts & statistics
                </p>
              </div>
            </div>

            <div className="ml-4 h-5 w-px bg-slate-200" />

            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-50 text-xs font-bold text-amber-600">
                4
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-800">
                  Discover Insights
                </p>

                <p className="text-[11px] text-slate-400">
                  Anomalies, forecasts & RCA
                </p>
              </div>
            </div>
          </div>

          <div className="mt-7 rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50 to-violet-50 p-4">
            <p className="text-xs font-bold text-indigo-900">
              Ready to explore your data?
            </p>

            <p className="mt-1.5 text-[11px] leading-5 text-indigo-700/80">
              Open a dataset and continue to analytics for a deeper view of
              your business data.
            </p>

            {currentDataset && (
              <button
                onClick={() =>
                  handleSelectAndOpen(currentDataset, "analytics")
                }
                className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-indigo-700 hover:text-indigo-900"
              >
                Open active dataset
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </aside>
      </section>
    </div>
  );
}