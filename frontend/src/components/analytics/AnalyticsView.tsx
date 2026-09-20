"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import {
  DatasetOverviewResponse,
  TimeSeriesResult,
  BreakdownResult,
  CorrelationResult,
  DatasetProfileResponse,
} from "../../lib/types";
import { ChartWrapper } from "../ChartWrapper";
import {
  BarChart3,
  Calendar,
  Layers,
  LineChart,
  PieChart,
  Grid,
  AlertCircle,
  Database,
  ArrowUpDown,
  RefreshCw,
} from "lucide-react";
import * as echarts from "echarts";

type AnalyticsSubTab =
  | "overview"
  | "time-series"
  | "breakdown"
  | "correlation";

export function AnalyticsView() {
  const { currentDataset, setActiveStep } = useAuth();

  const [activeTab, setActiveTab] =
    useState<AnalyticsSubTab>("overview");
  const [profile, setProfile] =
    useState<DatasetProfileResponse | null>(null);

  // Overview State
  const [overview, setOverview] =
    useState<DatasetOverviewResponse | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);

  // Time Series State
  const [tsDateCol, setTsDateCol] = useState<string>("");
  const [tsMetricCol, setTsMetricCol] = useState<string>("");
  const [tsGranularity, setTsGranularity] =
    useState<string>("month");
  const [tsAggregation, setTsAggregation] =
    useState<string>("sum");
  const [tsRollingWindow, setTsRollingWindow] =
    useState<number | null>(null);
  const [tsGrowth, setTsGrowth] = useState<boolean>(false);
  const [tsCumulative, setTsCumulative] =
    useState<boolean>(false);
  const [tsResult, setTsResult] =
    useState<TimeSeriesResult | null>(null);
  const [tsLoading, setTsLoading] = useState(false);

  // Breakdown State
  const [bdDimension, setBdDimension] = useState<string>("");
  const [bdMetricCol, setBdMetricCol] = useState<string>("");
  const [bdAggregation, setBdAggregation] =
    useState<string>("sum");
  const [bdTopN, setBdTopN] = useState<number>(10);
  const [bdResult, setBdResult] =
    useState<BreakdownResult | null>(null);
  const [bdLoading, setBdLoading] = useState(false);

  // Correlation State
  const [corrCols, setCorrCols] = useState<string[]>([]);
  const [corrMethod, setCorrMethod] =
    useState<"pearson" | "spearman">("pearson");
  const [corrResult, setCorrResult] =
    useState<CorrelationResult | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  // Load profile to discover column types
  useEffect(() => {
    if (!currentDataset) return;

    api
      .getProfile(currentDataset.id)
      .then((p) => {
        setProfile(p);

        /*
         * IMPORTANT:
         * Always use the exact column names from column_names
         * when communicating with the backend.
         *
         * This makes the application work with arbitrary datasets,
         * including columns containing spaces, underscores,
         * capitalization, hyphens, etc.
         */
        const getActualColumnName = (
          column: typeof p.columns[number]
        ) => {
          const index = p.columns.indexOf(column);
          return p.column_names[index] ?? column.name;
        };

        const dateCols = p.columns.filter(
          (c) =>
            c.classification === "datetime" ||
            c.inferred_datatype.includes("date")
        );

        const numCols = p.columns.filter(
          (c) =>
            c.classification === "numerical_continuous" ||
            c.classification === "numerical_discrete" ||
            c.classification === "numeric" ||
            c.inferred_datatype.includes("float") ||
            c.inferred_datatype.includes("int") ||
            c.inferred_datatype.includes("integer")
        );

        const catCols = p.columns.filter(
          (c) =>
            c.classification === "categorical" ||
            c.inferred_datatype === "string"
        );

        if (dateCols.length > 0) {
          setTsDateCol(getActualColumnName(dateCols[0]));
        } else if (p.column_names.length > 0) {
          setTsDateCol(p.column_names[0]);
        }

        if (numCols.length > 0) {
          const actualMetric =
            getActualColumnName(numCols[0]);

          setTsMetricCol(actualMetric);
          setBdMetricCol(actualMetric);

          setCorrCols(
            numCols
              .slice(0, 8)
              .map((column) =>
                getActualColumnName(column)
              )
          );
        }

        if (catCols.length > 0) {
          setBdDimension(
            getActualColumnName(catCols[0])
          );
        } else if (p.column_names.length > 0) {
          setBdDimension(p.column_names[0]);
        }
      })
      .catch(console.error);
  }, [currentDataset?.id]);

  // Load Overview when tab changes to overview
  useEffect(() => {
    if (!currentDataset || activeTab !== "overview")
      return;

    setOverviewLoading(true);
    setError(null);

    api
      .getOverview(currentDataset.id)
      .then(setOverview)
      .catch((err) => setError(err.message))
      .finally(() => setOverviewLoading(false));
  }, [currentDataset?.id, activeTab]);

  // Handle Time Series fetch
  async function fetchTimeSeries() {
    if (
      !currentDataset ||
      !tsDateCol ||
      !tsMetricCol
    )
      return;

    setTsLoading(true);
    setError(null);

    try {
      const res = await api.queryTimeSeries(
        currentDataset.id,
        {
          date_column: tsDateCol,
          metric_column: tsMetricCol,
          granularity: tsGranularity,
          aggregation: tsAggregation,
          rolling_window:
            tsRollingWindow || undefined,
          include_growth: tsGrowth,
          include_cumulative: tsCumulative,
        }
      );

      setTsResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setTsLoading(false);
    }
  }

  // Handle Breakdown fetch
  async function fetchBreakdown() {
    if (!currentDataset || !bdDimension)
      return;

    setBdLoading(true);
    setError(null);

    try {
      const res = await api.queryBreakdown(
        currentDataset.id,
        {
          dimension: bdDimension,
          metric_column:
            bdMetricCol || undefined,
          aggregation: bdAggregation,
          top_n: bdTopN,
          include_other: true,
        }
      );

      setBdResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBdLoading(false);
    }
  }

  // Handle Correlation fetch
  async function fetchCorrelation() {
    if (
      !currentDataset ||
      corrCols.length < 2
    ) {
      setError(
        "Please select at least 2 numeric columns for correlation."
      );
      return;
    }

    setCorrLoading(true);
    setError(null);

    try {
      const res = await api.queryCorrelation(
        currentDataset.id,
        {
          columns: corrCols,
          method: corrMethod,
        }
      );

      setCorrResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCorrLoading(false);
    }
  }

  if (!currentDataset) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-sm">
        <Database className="h-12 w-12 text-slate-300 mb-3" />

        <h3 className="text-lg font-bold text-slate-900">
          No Dataset Selected
        </h3>

        <p className="mt-1 text-sm text-slate-500 max-w-sm">
          Please select or upload a dataset to run
          aggregations, time-series, breakdowns, and
          correlation analysis.
        </p>

        <button
          onClick={() =>
            setActiveStep("dashboard")
          }
          className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Select Dataset
        </button>
      </div>
    );
  }

  // --- Construct ECharts Option for Time Series ---
  const timeSeriesChartOption: echarts.EChartsOption =
    {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
      },

      grid: {
        left: "4%",
        right: "4%",
        bottom: "10%",
        top: "12%",
        containLabel: true,
      },

      xAxis: {
        type: "category",
        data: tsResult
          ? tsResult.series.map(
              (p) => p.timestamp
            )
          : [],
        axisLabel: {
          color: "#64748b",
          rotate: 30,
        },
      },

      yAxis: [
        {
          type: "value",
          name: `${tsAggregation.toUpperCase()} (${tsMetricCol})`,
          axisLabel: { color: "#64748b" },
          splitLine: {
            lineStyle: {
              color: "#f1f5f9",
            },
          },
        },

        ...(tsGrowth
          ? [
              {
                type: "value" as const,
                name: "Growth %",
                axisLabel: {
                  formatter: "{value} %",
                  color: "#64748b",
                },
                splitLine: {
                  show: false,
                },
              },
            ]
          : []),
      ],

      series: [
        {
          name: "Metric Value",
          type: "line",
          smooth: true,
          data: tsResult
            ? tsResult.series.map(
                (p) => p.value
              )
            : [],
          itemStyle: {
            color: "#4f46e5",
          },
          areaStyle: {
            color:
              new echarts.graphic.LinearGradient(
                0,
                0,
                0,
                1,
                [
                  {
                    offset: 0,
                    color:
                      "rgba(79, 70, 229, 0.25)",
                  },
                  {
                    offset: 1,
                    color:
                      "rgba(79, 70, 229, 0.0)",
                  },
                ]
              ),
          },
        },

        ...(tsRollingWindow && tsResult
          ? [
              {
                name: `${tsRollingWindow}-Period Rolling Avg`,
                type: "line" as const,
                smooth: true,
                data: tsResult.series.map(
                  (p) =>
                    p.rolling_average ?? null
                ),
                itemStyle: {
                  color: "#f59e0b",
                },
                lineStyle: {
                  width: 2,
                  type: "dashed" as const,
                },
              },
            ]
          : []),

        ...(tsCumulative && tsResult
          ? [
              {
                name: "Cumulative Total",
                type: "line" as const,
                smooth: true,
                data: tsResult.series.map(
                  (p) =>
                    p.cumulative_value ?? null
                ),
                itemStyle: {
                  color: "#10b981",
                },
                lineStyle: {
                  width: 2,
                },
              },
            ]
          : []),

        ...(tsGrowth && tsResult
          ? [
              {
                name: "Growth Rate %",
                type: "bar" as const,
                yAxisIndex: 1,
                data: tsResult.series.map(
                  (p) =>
                    p.growth_rate_pct ?? null
                ),
                itemStyle: {
                  color:
                    "rgba(244, 63, 94, 0.6)",
                },
              },
            ]
          : []),
      ],
    };

  // --- Construct ECharts Option for Breakdown ---
  const breakdownChartOption: echarts.EChartsOption =
    {
      tooltip: {
        trigger: "item",
        formatter: "{b}: {c} ({d}%)",
      },

      grid: {
        left: "4%",
        right: "4%",
        bottom: "5%",
        top: "5%",
        containLabel: true,
      },

      series: [
        {
          name: bdDimension,
          type: "pie",
          radius: ["40%", "70%"],
          avoidLabelOverlap: true,

          itemStyle: {
            borderRadius: 6,
            borderColor: "#fff",
            borderWidth: 2,
          },

          label: {
            show: true,
            formatter: "{b}: {d}%",
            fontSize: 11,
          },

          data: bdResult
            ? bdResult.items.map((it) => ({
                name: it.category,
                value: it.value,
              }))
            : [],
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
              Business Analytics Engine
            </span>

            <span className="text-xs text-slate-400">
              •
            </span>

            <span className="text-xs font-medium text-slate-500">
              {currentDataset.name} (
              {currentDataset.is_cleaned
                ? "Cleaned"
                : "Raw"}
              )
            </span>
          </div>

          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Multi-Dimensional Analytics
          </h1>

          <p className="text-xs text-slate-500 mt-0.5">
            Interactive temporal time-series,
            segment share breakdowns, and
            Pearson/Spearman correlation matrices.
          </p>
        </div>

        {/* Sub-Tabs */}
        <div className="flex items-center rounded-lg bg-slate-100 p-1 text-xs font-semibold">
          <button
            onClick={() =>
              setActiveTab("overview")
            }
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              activeTab === "overview"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            <span>Overview</span>
          </button>

          <button
            onClick={() => {
              setActiveTab("time-series");

              if (!tsResult)
                fetchTimeSeries();
            }}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              activeTab === "time-series"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <LineChart className="h-3.5 w-3.5" />
            <span>Time Series</span>
          </button>

          <button
            onClick={() => {
              setActiveTab("breakdown");

              if (!bdResult)
                fetchBreakdown();
            }}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              activeTab === "breakdown"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <PieChart className="h-3.5 w-3.5" />
            <span>Breakdown</span>
          </button>

          <button
            onClick={() => {
              setActiveTab("correlation");

              if (!corrResult)
                fetchCorrelation();
            }}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              activeTab === "correlation"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Grid className="h-3.5 w-3.5" />
            <span>Correlation</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-600 mt-0.5" />

          <div className="text-sm">
            <p className="font-semibold">
              Query Error
            </p>

            <p className="mt-0.5 text-xs text-rose-700">
              {error}
            </p>
          </div>
        </div>
      )}

      {/* --- TAB 1: OVERVIEW --- */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {overviewLoading ? (
            <div className="py-16 text-center text-slate-500">
              <RefreshCw className="mx-auto h-8 w-8 animate-spin text-indigo-600 mb-2" />

              <p className="text-sm font-semibold">
                Aggregating dataset overview KPIs...
              </p>
            </div>
          ) : overview ? (
            <>
              {/* Temporal KPI Banner */}
              {overview.temporal_kpi && (
                <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-indigo-50 p-2.5 text-indigo-600">
                      <Calendar className="h-5 w-5" />
                    </div>

                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Temporal Window
                      </h4>

                      <p className="text-sm font-bold text-slate-900 mt-0.5">
                        {overview.temporal_kpi.min_date} —{" "}
                        {overview.temporal_kpi.max_date}
                      </p>
                    </div>
                  </div>

                  <div className="text-right">
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">
                      {overview.temporal_kpi.range_days}{" "}
                      Days Covered
                    </span>
                  </div>
                </div>
              )}

              {/* Numeric KPIs */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  Numeric Metrics Summary
                </h3>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(
                    overview.numeric_kpis
                  ).map(([col, stats]) => (
                    <div
                      key={col}
                      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm font-bold text-slate-900">
                          {col}
                        </span>

                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                          {(stats?.count ?? 0).toLocaleString()}{" "}
                          rows
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-xs border-t border-slate-100 pt-2">
                        <div>
                          <span className="text-slate-400">
                            Sum:
                          </span>

                          <p className="font-semibold text-slate-800">
                            {stats?.sum != null
                              ? stats.sum.toLocaleString()
                              : "—"}
                          </p>
                        </div>

                        <div>
                          <span className="text-slate-400">
                            Mean:
                          </span>

                          <p className="font-semibold text-slate-800">
                            {stats?.mean != null
                              ? stats.mean.toFixed(2)
                              : "—"}
                          </p>
                        </div>

                        <div>
                          <span className="text-slate-400">
                            Min / Max:
                          </span>

                          <p className="font-semibold text-slate-800">
                            {stats?.min != null
                              ? stats.min
                              : "—"}{" "}
                            /{" "}
                            {stats?.max != null
                              ? stats.max
                              : "—"}
                          </p>
                        </div>

                        <div>
                          <span className="text-slate-400">
                            Std Dev:
                          </span>

                          <p className="font-semibold text-slate-800">
                            {stats?.std != null
                              ? stats.std.toFixed(2)
                              : "—"}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Top Dimensions */}
              {Object.keys(
                overview.top_dimension_kpis
              ).length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                    Top Categorical Dimensions
                  </h3>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {Object.entries(
                      overview.top_dimension_kpis
                    ).map(([dim, cats]) => (
                      <div
                        key={dim}
                        className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
                      >
                        <h4 className="font-mono text-sm font-bold text-slate-900 border-b border-slate-100 pb-2 mb-3">
                          {dim}
                        </h4>

                        <div className="space-y-2">
                          {cats
                            .slice(0, 5)
                            .map((cat) => (
                              <div
                                key={cat.category}
                                className="flex justify-between text-xs"
                              >
                                <span
                                  className="text-slate-700 truncate mr-2"
                                  title={cat.category}
                                >
                                  {cat.category ||
                                    "(blank)"}
                                </span>

                                <span className="font-semibold text-slate-900">
                                  {(
                                    cat.count ?? 0
                                  ).toLocaleString()}
                                </span>
                              </div>
                            ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* --- TAB 2: TIME SERIES --- */}
      {activeTab === "time-series" && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {/* Date Column */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Date Column
                </label>

                <select
                  value={tsDateCol}
                  onChange={(e) =>
                    setTsDateCol(e.target.value)
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  {profile?.column_names.map(
                    (columnName) => (
                      <option
                        key={columnName}
                        value={columnName}
                      >
                        {columnName}
                      </option>
                    )
                  )}
                </select>
              </div>

              {/* Metric Column */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Metric
                </label>

                <select
                  value={tsMetricCol}
                  onChange={(e) =>
                    setTsMetricCol(e.target.value)
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  {profile?.column_names.map(
                    (columnName) => (
                      <option
                        key={columnName}
                        value={columnName}
                      >
                        {columnName}
                      </option>
                    )
                  )}
                </select>
              </div>

              {/* Granularity */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Granularity
                </label>

                <select
                  value={tsGranularity}
                  onChange={(e) =>
                    setTsGranularity(
                      e.target.value
                    )
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  <option value="day">
                    Daily
                  </option>

                  <option value="week">
                    Weekly
                  </option>

                  <option value="month">
                    Monthly
                  </option>

                  <option value="quarter">
                    Quarterly
                  </option>

                  <option value="year">
                    Yearly
                  </option>
                </select>
              </div>

              {/* Aggregation */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Aggregation
                </label>

                <select
                  value={tsAggregation}
                  onChange={(e) =>
                    setTsAggregation(
                      e.target.value
                    )
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  <option value="sum">
                    Sum
                  </option>

                  <option value="mean">
                    Mean
                  </option>

                  <option value="median">
                    Median
                  </option>

                  <option value="count">
                    Count
                  </option>

                  <option value="min">
                    Min
                  </option>

                  <option value="max">
                    Max
                  </option>
                </select>
              </div>

              {/* Rolling Window */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Rolling Average
                </label>

                <select
                  value={tsRollingWindow ?? ""}
                  onChange={(e) =>
                    setTsRollingWindow(
                      e.target.value
                        ? Number(
                            e.target.value
                          )
                        : null
                    )
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  <option value="">
                    None
                  </option>

                  <option value="3">
                    3-Period
                  </option>

                  <option value="7">
                    7-Period
                  </option>

                  <option value="14">
                    14-Period
                  </option>

                  <option value="30">
                    30-Period
                  </option>
                </select>
              </div>

              {/* Submit Button */}
              <div className="flex items-end">
                <button
                  onClick={fetchTimeSeries}
                  disabled={tsLoading}
                  className="w-full rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {tsLoading
                    ? "Resampling..."
                    : "Run Query"}
                </button>
              </div>
            </div>

            {/* Toggles */}
            <div className="mt-3 flex items-center gap-6 border-t border-slate-100 pt-3 text-xs text-slate-600">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={tsGrowth}
                  onChange={(e) =>
                    setTsGrowth(
                      e.target.checked
                    )
                  }
                  className="rounded text-indigo-600"
                />

                <span>
                  Include Growth Rate %
                </span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={tsCumulative}
                  onChange={(e) =>
                    setTsCumulative(
                      e.target.checked
                    )
                  }
                  className="rounded text-indigo-600"
                />

                <span>
                  Include Cumulative Total
                </span>
              </label>
            </div>
          </div>

          {/* Chart Card */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-base font-bold text-slate-900 mb-2">
              Time Series:{" "}
              {tsAggregation.toUpperCase()} of{" "}
              {tsMetricCol} by{" "}
              {tsGranularity}
            </h3>

            {tsResult &&
            tsResult.series.length > 0 ? (
              <ChartWrapper
                option={timeSeriesChartOption}
                height="400px"
                loading={tsLoading}
              />
            ) : (
              <div className="py-20 text-center text-slate-400">
                Click "Run Query" to visualize
                the metric time series
              </div>
            )}
          </div>
        </div>
      )}

      {/* --- TAB 3: BREAKDOWN --- */}
      {activeTab === "breakdown" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {/* Dimension */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Dimension
                </label>

                <select
                  value={bdDimension}
                  onChange={(e) =>
                    setBdDimension(
                      e.target.value
                    )
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  {profile?.column_names.map(
                    (columnName) => (
                      <option
                        key={columnName}
                        value={columnName}
                      >
                        {columnName}
                      </option>
                    )
                  )}
                </select>
              </div>

              {/* Metric */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Metric
                </label>

                <select
                  value={bdMetricCol}
                  onChange={(e) =>
                    setBdMetricCol(
                      e.target.value
                    )
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  <option value="">
                    (Row Count)
                  </option>

                  {profile?.column_names.map(
                    (columnName) => (
                      <option
                        key={columnName}
                        value={columnName}
                      >
                        {columnName}
                      </option>
                    )
                  )}
                </select>
              </div>

              {/* Top N Segments */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Top N Segments
                </label>

                <input
                  type="number"
                  min={3}
                  max={50}
                  value={bdTopN}
                  onChange={(e) =>
                    setBdTopN(
                      Number(e.target.value)
                    )
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                />
              </div>

              {/* Aggregation */}
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Aggregation
                </label>

                <select
                  value={bdAggregation}
                  onChange={(e) =>
                    setBdAggregation(
                      e.target.value
                    )
                  }
                  className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none"
                >
                  <option value="sum">
                    Sum
                  </option>

                  <option value="mean">
                    Mean
                  </option>

                  <option value="count">
                    Count
                  </option>
                </select>
              </div>

              <div className="flex items-end">
                <button
                  onClick={fetchBreakdown}
                  disabled={bdLoading}
                  className="w-full rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {bdLoading
                    ? "Calculating..."
                    : "Compute Share"}
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Donut Chart */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-900 mb-4">
                Share of Total:{" "}
                {bdDimension}
              </h3>

              {bdResult &&
              bdResult.items.length > 0 ? (
                <ChartWrapper
                  option={breakdownChartOption}
                  height="360px"
                  loading={bdLoading}
                />
              ) : (
                <div className="py-20 text-center text-slate-400">
                  Compute breakdown to view
                  segment share
                </div>
              )}
            </div>

            {/* Table */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm overflow-hidden">
              <h3 className="text-sm font-bold text-slate-900 mb-4">
                Segment Values
              </h3>

              {bdResult &&
              bdResult.items.length > 0 ? (
                <div className="overflow-y-auto max-h-[360px]">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-slate-200 bg-slate-50 uppercase text-slate-500">
                      <tr>
                        <th className="px-4 py-2">
                          Category
                        </th>

                        <th className="px-4 py-2">
                          Value
                        </th>

                        <th className="px-4 py-2 text-right">
                          Share %
                        </th>
                      </tr>
                    </thead>

                    <tbody className="divide-y divide-slate-100">
                      {bdResult.items.map(
                        (it) => (
                          <tr
                            key={it.category}
                            className="hover:bg-slate-50"
                          >
                            <td className="px-4 py-2 font-medium text-slate-800">
                              {it.category}
                            </td>

                            <td className="px-4 py-2 font-mono text-slate-600">
                              {it.value.toLocaleString()}
                            </td>

                            <td className="px-4 py-2 text-right font-bold text-indigo-600">
                              {it.percentage_of_total.toFixed(
                                1
                              )}
                              %
                            </td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-20 text-center text-slate-400">
                  No data computed
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* --- TAB 4: CORRELATION MATRIX --- */}
      {activeTab === "correlation" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-500 mb-1">
                  Method
                </label>

                <div className="flex items-center gap-3 text-xs font-semibold">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="corrMethod"
                      value="pearson"
                      checked={
                        corrMethod ===
                        "pearson"
                      }
                      onChange={() =>
                        setCorrMethod(
                          "pearson"
                        )
                      }
                      className="text-indigo-600"
                    />

                    <span>
                      Pearson (linear)
                    </span>
                  </label>

                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="corrMethod"
                      value="spearman"
                      checked={
                        corrMethod ===
                        "spearman"
                      }
                      onChange={() =>
                        setCorrMethod(
                          "spearman"
                        )
                      }
                      className="text-indigo-600"
                    />

                    <span>
                      Spearman (rank)
                    </span>
                  </label>
                </div>
              </div>

              <button
                onClick={fetchCorrelation}
                disabled={corrLoading}
                className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {corrLoading
                  ? "Calculating Correlation..."
                  : "Compute Correlation Matrix"}
              </button>
            </div>
          </div>

          {/* Matrix Grid */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm overflow-x-auto">
            <h3 className="text-base font-bold text-slate-900 mb-4">
              Pairwise Correlation Heatmap (
              {corrMethod.toUpperCase()})
            </h3>

            {corrResult ? (
              <table className="w-full border-collapse text-center text-xs">
                <thead>
                  <tr>
                    <th className="p-2 text-left font-semibold text-slate-500">
                      Metric
                    </th>

                    {corrResult.columns.map(
                      (col) => (
                        <th
                          key={col}
                          className="p-2 font-mono font-semibold text-slate-700"
                        >
                          {col}
                        </th>
                      )
                    )}
                  </tr>
                </thead>

                <tbody>
                  {corrResult.columns.map(
                    (rowCol) => (
                      <tr
                        key={rowCol}
                        className="border-t border-slate-100"
                      >
                        <td className="p-2 text-left font-mono font-semibold text-slate-800">
                          {rowCol}
                        </td>

                        {corrResult.columns.map(
                          (colCol) => {
                            const val =
                              corrResult
                                .correlation_matrix[
                                rowCol
                              ]?.[colCol];

                            let bgColor =
                              "bg-slate-50";
                            let textColor =
                              "text-slate-700";

                            if (
                              val !== null &&
                              val !== undefined
                            ) {
                              if (val >= 0.7) {
                                bgColor =
                                  "bg-indigo-600";
                                textColor =
                                  "text-white font-bold";
                              } else if (
                                val >= 0.3
                              ) {
                                bgColor =
                                  "bg-indigo-200";
                                textColor =
                                  "text-indigo-900 font-semibold";
                              } else if (
                                val > -0.3
                              ) {
                                bgColor =
                                  "bg-slate-100";
                                textColor =
                                  "text-slate-700";
                              } else if (
                                val > -0.7
                              ) {
                                bgColor =
                                  "bg-rose-200";
                                textColor =
                                  "text-rose-900 font-semibold";
                              } else {
                                bgColor =
                                  "bg-rose-600";
                                textColor =
                                  "text-white font-bold";
                              }
                            }

                            return (
                              <td
                                key={colCol}
                                className="p-1.5"
                              >
                                <div
                                  className={`rounded p-2 font-mono transition ${bgColor} ${textColor}`}
                                >
                                  {val !== null &&
                                  val !==
                                    undefined
                                    ? val.toFixed(
                                        2
                                      )
                                    : "NaN"}
                                </div>
                              </td>
                            );
                          }
                        )}
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            ) : (
              <div className="py-20 text-center text-slate-400">
                Click "Compute Correlation Matrix"
                to calculate pairwise correlation
                coefficients
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}