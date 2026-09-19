/**
 * Frontend TypeScript contracts mirroring Phase 0-11 FastAPI Pydantic models.
 */

// --- Auth & User ---
export interface UserResponse {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// --- Organizations & RBAC ---
export type OrgRole = "ADMIN" | "ANALYST" | "MANAGER" | "VIEWER";

export interface OrganizationResponse {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
}

export interface OrganizationMemberResponse {
  user_id: string;
  organization_id: string;
  role: OrgRole;
  user: UserResponse;
}

// --- Datasets ---
export type DatasetStatus = "uploaded" | "cleaned" | "error";

export interface DatasetResponse {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  original_filename: string;
  file_type: string;
  file_size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  status: DatasetStatus;
  is_cleaned: boolean;
  created_at: string;
  updated_at: string;
}

export interface DatasetListResponse {
  items: DatasetResponse[];
  total: number;
  limit: number;
  offset: number;
}

// --- Profiling & 5D Quality Score ---
export interface CategoryFrequency {
  value: string;
  count: number;
  percentage: number;
}

export interface CategoricalStats {
  num_categories: number;
  top_categories: CategoryFrequency[];
}

export interface NumericStats {
  min: number;
  max: number;
  mean: number;
  median: number;
  std_dev: number | null;
  percentiles: Record<string, number>;
}

export interface DatetimeStats {
  min_date: string | null;
  max_date: string | null;
  date_range_days: number | null;
  invalid_date_count: number;
}

export interface ColumnProfile {
  name: string;
  inferred_datatype: string;
  classification: "identifier" | "categorical" | "numerical_continuous" | "numerical_discrete" | "datetime" | string;
  null_count: number;
  null_percentage: number;
  unique_count: number;
  unique_percentage: number;
  sample_values: unknown[];
  numeric_stats?: NumericStats | null;
  categorical_stats?: CategoricalStats | null;
  datetime_stats?: DatetimeStats | null;
}

export interface DataQualityComponents {
  completeness: number;      // 30%
  uniqueness: number;        // 25%
  type_consistency: number;  // 20%
  date_validity: number;     // 15%
  reasonableness: number;    // 10%
}

export interface DataQualityMetrics {
  total_cells: number;
  missing_cells: number;
  missing_cells_pct: number;
  duplicate_rows: number;
  duplicate_rows_pct: number;
  inconsistent_type_cells: number;
  invalid_date_count: number;
  suspicious_value_count: number;
}

export interface DataQualityScore {
  score: number;
  grade: string;
  formula: string;
  components: DataQualityComponents;
  metrics: DataQualityMetrics;
}

export interface DatasetProfileResponse {
  dataset_id: string;
  row_count: number;
  column_count: number;
  column_names: string[];
  memory_size_bytes: number;
  duplicate_row_count: number;
  duplicate_row_percentage: number;
  total_missing_cells: number;
  missing_cells_percentage: number;
  columns: ColumnProfile[];
  quality_score: DataQualityScore;
}

// --- Data Cleaning ---
export interface CleaningConfig {
  remove_duplicates: boolean;
  numeric_strategy: "median" | "mean" | "zero" | "none";
  categorical_strategy: "mode" | "unknown" | "none";
  normalize_column_names: boolean;
  normalize_categories: boolean;
  outlier_handling: "detect_only" | "cap";
}

export interface DatatypeChange {
  column: string;
  from_type: string;
  to_type: string;
  success_count: number;
  failure_count: number;
}

export interface OutlierSummary {
  column: string;
  count: number;
  method: string;
  lower_bound: number | null;
  upper_bound: number | null;
  sample_outliers: number[];
}

export interface ReferentialSummary {
  column: string;
  missing_count: number;
  invalid_reference_count: number;
  issues: string[];
}

export interface CleaningPreviewResponse {
  dataset_id: string;
  rows_before: number;
  rows_after_estimate: number;
  duplicates_detected: number;
  duplicates_percentage: number;
  missing_values_detected: Record<string, number>;
  columns_to_modify: string[];
  datatype_changes: DatatypeChange[];
  categorical_normalizations: Record<string, Record<string, string>>;
  invalid_values: Record<string, number>;
  outlier_summary: Record<string, OutlierSummary>;
  referential_issues: Record<string, ReferentialSummary>;
  warnings: string[];
  proposed_actions: string[];
}

export interface CleaningReportResponse {
  dataset_id: string;
  rows_before: number;
  rows_after: number;
  duplicates_removed: number;
  missing_values_handled: Record<string, number>;
  datatype_changes: DatatypeChange[];
  outliers_handled: Record<string, OutlierSummary>;
  status: string;
  created_at: string;
}

// --- Analytics ---
export interface DatasetOverviewResponse {
  dataset_id: string;
  is_cleaned: boolean;
  row_count: number;
  column_count: number;
  numeric_kpis: Record<string, {
    count: number;
    sum?: number;
    mean?: number;
    median?: number;
    min?: number;
    max?: number;
    std?: number;
  }>;
  temporal_kpi: {
    column?: string;
    min_date?: string;
    max_date?: string;
    range_days?: number;
  } | null;
  top_dimension_kpis: Record<string, Array<{ category: string; count: number }>>;
}

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
  rolling_average?: number | null;
  cumulative_value?: number | null;
  growth_rate_pct?: number | null;
}

export interface TimeSeriesResult {
  dataset_id: string;
  is_cleaned: boolean;
  date_column: string;
  metric_column: string;
  granularity: string;
  series: TimeSeriesPoint[];
}

export interface BreakdownItem {
  category: string;
  value: number;
  percentage_of_total: number;
}

export interface BreakdownResult {
  dataset_id: string;
  is_cleaned: boolean;
  dimension: string;
  metric: string;
  total_value: number;
  items: BreakdownItem[];
}

export interface CrossTabResult {
  dataset_id: string;
  is_cleaned: boolean;
  row_dimension: string;
  column_dimension: string;
  row_values: string[];
  column_values: string[];
  matrix: number[][];
}

export interface CorrelationResult {
  dataset_id: string;
  is_cleaned: boolean;
  columns: string[];
  correlation_matrix: Record<string, Record<string, number | null>>;
}

export interface AggregationResult {
  dataset_id: string;
  is_cleaned: boolean;
  total_rows: number;
  data: Record<string, unknown>[];
}

// --- Machine Learning: Anomalies & Forecasts ---
export type AnomalySeverity = "low" | "medium" | "high" | "critical";

export interface AnomalyItemResponse {
  id?: string;
  metric_name: string;
  detected_at: string;
  severity: AnomalySeverity;
  value: number | null;
  expected_value: number | null;
  deviation_pct: number | null;
  description: string | null;
  algorithm: string | null;
}

export interface AnomalyListResponse {
  dataset_id: string;
  metric_name: string;
  total_anomalies: number;
  anomalies: AnomalyItemResponse[];
  provenance: Record<string, unknown>;
}

export interface ForecastPointResponse {
  forecast_date: string;
  predicted_value: number;
  lower_bound: number | null;
  upper_bound: number | null;
  model_name?: string | null;
}

export interface ForecastResponse {
  dataset_id: string;
  metric_name: string;
  horizon_days: number;
  model_name: string;
  generated_at: string;
  forecasts: ForecastPointResponse[];
  provenance: Record<string, unknown>;
}

export interface MLSummaryResponse {
  dataset_id: string;
  total_anomalies_active: number;
  anomalies_by_severity: Record<string, number>;
  forecasts_active_count: number;
  metrics_analyzed: string[];
}

// --- Root-Cause Analysis (RCA) ---
export interface StatisticalScore {
  z_score: number | null;
  baseline_mean: number;
  baseline_std: number | null;
  is_significant: boolean;
  variance_note: string | null;
}

export interface SegmentDriver {
  dataset_id: string;
  anomaly_id?: string | null;
  dimension: string;
  segment_value: string;
  baseline_value: number;
  event_value: number;
  delta: number;
  contribution_pct: number | null;
  growth_pct: number;
  statistical_score: StatisticalScore;
  event_window: Record<string, string>;
  baseline_window: Record<string, string>;
  metric_name: string;
}

export interface DimensionDriverBreakdown {
  dimension: string;
  total_segments: number;
  top_positive_drivers: SegmentDriver[];
  top_negative_drivers: SegmentDriver[];
  coverage_pct: number;
}

export interface SecondaryMetricImpact {
  metric_name: string;
  baseline_value: number;
  event_value: number;
  delta: number;
  growth_pct: number;
  direction: "concordant" | "divergent" | "neutral";
  elasticity: number | null;
  elasticity_status: string;
}

export interface WaterfallReconciliation {
  sum_segment_deltas_full: number;
  total_metric_delta: number;
  discrepancy: number;
  is_reconciled: boolean;
  truncated_display_count: number;
  total_segments_count: number;
  reconciliation_warning: string | null;
}

export interface RCAResponse {
  dataset_id: string;
  anomaly_id?: string | null;
  metric_name: string;
  aggregation: string;
  event_window: Record<string, string>;
  baseline_window: Record<string, string>;
  total_delta: number;
  percentage_change: number;
  contribution_status: string;
  contribution_explanation?: string | null;
  reconciliation: WaterfallReconciliation;
  primary_drivers: SegmentDriver[];
  dimension_breakdowns: DimensionDriverBreakdown[];
  secondary_metrics: SecondaryMetricImpact[];
  narrative_summary: string;
  provenance: Record<string, unknown>;
}
