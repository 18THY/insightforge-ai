/**
 * InsightForge AI - Centralized Strongly-Typed API Client
 * Interfaces directly with FastAPI backend at http://localhost:8000
 */

import {
  AggregationResult,
  AnomalyListResponse,
  BreakdownResult,
  CleaningConfig,
  CleaningPreviewResponse,
  CleaningReportResponse,
  CorrelationResult,
  CrossTabResult,
  DatasetListResponse,
  DatasetOverviewResponse,
  DatasetProfileResponse,
  DatasetResponse,
  ForecastResponse,
  MLSummaryResponse,
  OrganizationMemberResponse,
  OrganizationResponse,
  RCAResponse,
  TimeSeriesResult,
  TokenResponse,
  UserResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let currentAccessToken: string | null = null;
let currentRefreshToken: string | null = null;

export function setAuthTokens(accessToken: string | null, refreshToken: string | null) {
  currentAccessToken = accessToken;
  currentRefreshToken = refreshToken;
  if (typeof window !== "undefined") {
    if (accessToken) {
      localStorage.setItem("if_access_token", accessToken);
    } else {
      localStorage.removeItem("if_access_token");
    }
    if (refreshToken) {
      localStorage.setItem("if_refresh_token", refreshToken);
    } else {
      localStorage.removeItem("if_refresh_token");
    }
  }
}

export function loadStoredTokens(): { accessToken: string | null; refreshToken: string | null } {
  if (typeof window === "undefined") {
    return { accessToken: null, refreshToken: null };
  }
  const accessToken = localStorage.getItem("if_access_token");
  const refreshToken = localStorage.getItem("if_refresh_token");
  currentAccessToken = accessToken;
  currentRefreshToken = refreshToken;
  return { accessToken, refreshToken };
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (currentAccessToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${currentAccessToken}`);
  }

  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401 && currentRefreshToken && endpoint !== "/auth/refresh" && endpoint !== "/auth/login") {
    // Attempt token rotation
    try {
      const refreshRes = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      });
      if (refreshRes.ok) {
        const tokens: TokenResponse = await refreshRes.json();
        setAuthTokens(tokens.access_token, tokens.refresh_token);
        // Retry original request
        headers.set("Authorization", `Bearer ${tokens.access_token}`);
        const retryRes = await fetch(url, { ...options, headers });
        if (!retryRes.ok) {
          const err = await retryRes.json().catch(() => ({ detail: retryRes.statusText }));
          throw new Error(err.detail || `Request failed with status ${retryRes.status}`);
        }
        return retryRes.json();
      }
    } catch {
      setAuthTokens(null, null);
    }
  }

  if (!response.ok) {
    let errorDetail = `Error ${response.status}: ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (typeof errJson.detail === "string") {
        errorDetail = errJson.detail;
      } else if (Array.isArray(errJson.detail)) {
        errorDetail = errJson.detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join(", ");
      } else if (errJson.message) {
        errorDetail = errJson.message;
      }
    } catch {
      // response was not JSON
    }
    throw new Error(errorDetail);
  }

  if (response.status === 204) {
    return null as unknown as T;
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// API Client Definition
// ---------------------------------------------------------------------------
export const api = {
  // --- Auth ---
  async register(email: string, password: string, fullName?: string): Promise<UserResponse> {
    return request<UserResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName || null }),
    });
  },

  async login(email: string, password: string): Promise<TokenResponse> {
    const data = await request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setAuthTokens(data.access_token, data.refresh_token);
    return data;
  },

  async getMe(): Promise<UserResponse> {
    return request<UserResponse>("/auth/me");
  },

  async logout(): Promise<{ message: string }> {
    const refreshToken = currentRefreshToken || "";
    try {
      if (refreshToken) {
        await request<{ message: string }>("/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      }
    } finally {
      setAuthTokens(null, null);
    }
    return { message: "Logged out" };
  },

  // --- Organizations ---
  async listOrgs(): Promise<OrganizationResponse[]> {
    return request<OrganizationResponse[]>("/organizations");
  },

  async createOrg(name: string, slug?: string): Promise<OrganizationResponse> {
    const generatedSlug = slug || name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    return request<OrganizationResponse>("/organizations", {
      method: "POST",
      body: JSON.stringify({ name, slug: generatedSlug }),
    });
  },

  async getOrg(orgId: string): Promise<OrganizationResponse> {
    return request<OrganizationResponse>(`/organizations/${orgId}`);
  },

  async getOrgMembers(orgId: string): Promise<OrganizationMemberResponse[]> {
    return request<OrganizationMemberResponse[]>(`/organizations/${orgId}/members`);
  },

  // --- Datasets ---
  async listDatasets(orgId: string, limit = 100, offset = 0): Promise<DatasetListResponse> {
    return request<DatasetListResponse>(`/datasets?organization_id=${orgId}&limit=${limit}&offset=${offset}`);
  },

  async getDataset(datasetId: string): Promise<DatasetResponse> {
    return request<DatasetResponse>(`/datasets/${datasetId}`);
  },

  async uploadDataset(
    orgId: string,
    file: File,
    name: string,
    description?: string
  ): Promise<DatasetResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("organization_id", orgId);
    formData.append("name", name);
    if (description) {
      formData.append("description", description);
    }
    return request<DatasetResponse>("/datasets/upload", {
      method: "POST",
      body: formData,
    });
  },

  async deleteDataset(datasetId: string): Promise<void> {
    return request<void>(`/datasets/${datasetId}`, {
      method: "DELETE",
    });
  },

  // --- Profiling ---
  async getProfile(datasetId: string): Promise<DatasetProfileResponse> {
    return request<DatasetProfileResponse>(`/datasets/${datasetId}/profile`);
  },

  // --- Cleaning ---
  async previewCleaning(datasetId: string, config?: CleaningConfig): Promise<CleaningPreviewResponse> {
    return request<CleaningPreviewResponse>(`/datasets/${datasetId}/clean/preview`, {
      method: "POST",
      body: config ? JSON.stringify(config) : undefined,
    });
  },

  async applyCleaning(datasetId: string, config?: CleaningConfig): Promise<CleaningReportResponse> {
    return request<CleaningReportResponse>(`/datasets/${datasetId}/clean/apply`, {
      method: "POST",
      body: config ? JSON.stringify(config) : undefined,
    });
  },

  // --- Analytics ---
  async getOverview(datasetId: string): Promise<DatasetOverviewResponse> {
    return request<DatasetOverviewResponse>(`/datasets/${datasetId}/analytics/overview`);
  },

  async queryTimeSeries(
    datasetId: string,
    query: {
      date_column: string;
      metric_column: string;
      aggregation?: string;
      granularity?: string;
      rolling_window?: number | null;
      include_cumulative?: boolean;
      include_growth?: boolean;
    }
  ): Promise<TimeSeriesResult> {
    return request<TimeSeriesResult>(`/datasets/${datasetId}/analytics/time-series`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  async queryBreakdown(
    datasetId: string,
    query: {
      dimension: string;
      metric_column?: string | null;
      aggregation?: string;
      top_n?: number;
      include_other?: boolean;
    }
  ): Promise<BreakdownResult> {
    return request<BreakdownResult>(`/datasets/${datasetId}/analytics/breakdown`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  async queryCrosstab(
    datasetId: string,
    query: {
      row_dimension: string;
      column_dimension: string;
      metric_column?: string | null;
      aggregation?: string;
    }
  ): Promise<CrossTabResult> {
    return request<CrossTabResult>(`/datasets/${datasetId}/analytics/crosstab`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  async queryCorrelation(
    datasetId: string,
    query: {
      columns?: string[];
      method?: "pearson" | "spearman";
    }
  ): Promise<CorrelationResult> {
    return request<CorrelationResult>(`/datasets/${datasetId}/analytics/correlation`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  async queryAggregation(
    datasetId: string,
    query: {
      metrics: Array<{ column: string; aggregation: string; alias?: string }>;
      dimensions?: string[];
      limit?: number;
    }
  ): Promise<AggregationResult> {
    return request<AggregationResult>(`/datasets/${datasetId}/analytics/aggregate`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  // --- Machine Learning: Anomalies & Forecasts ---
  async detectAnomalies(
    datasetId: string,
    query: {
      date_column: string;
      metric_column: string;
      aggregation?: "sum" | "mean";
      cadence?: "D" | "W" | "M";
      method?: "statistical" | "isolation_forest";
      sensitivity?: "low" | "medium" | "high";
      window_size?: number;
      persist?: boolean;
    }
  ): Promise<AnomalyListResponse> {
    return request<AnomalyListResponse>(`/datasets/${datasetId}/ml/anomalies/detect`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  async listAnomalies(
    datasetId: string,
    metricName?: string,
    severity?: string
  ): Promise<AnomalyListResponse> {
    const params = new URLSearchParams();
    if (metricName) params.append("metric_name", metricName);
    if (severity) params.append("severity", severity);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request<AnomalyListResponse>(`/datasets/${datasetId}/ml/anomalies${qs}`);
  },

  async generateForecast(
    datasetId: string,
    query: {
      date_column: string;
      metric_column: string;
      aggregation?: "sum" | "mean";
      cadence?: "D" | "W" | "M";
      horizon_days?: number;
      allow_negative?: boolean;
      persist?: boolean;
    }
  ): Promise<ForecastResponse> {
    return request<ForecastResponse>(`/datasets/${datasetId}/ml/forecasts/generate`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  async getForecasts(datasetId: string, metricName?: string): Promise<ForecastResponse> {
    const qs = metricName ? `?metric_name=${encodeURIComponent(metricName)}` : "";
    return request<ForecastResponse>(`/datasets/${datasetId}/ml/forecasts${qs}`);
  },

  async getMLSummary(datasetId: string): Promise<MLSummaryResponse> {
    return request<MLSummaryResponse>(`/datasets/${datasetId}/ml/summary`);
  },

  // --- Root-Cause Analysis (RCA) ---
  async analyzeRCA(
    datasetId: string,
    query: {
      anomaly_id?: string | null;
      metric_column?: string | null;
      date_column?: string | null;
      aggregation?: "sum" | "avg" | "count";
      event_start?: string | null;
      event_end?: string | null;
      baseline_start?: string | null;
      baseline_end?: string | null;
      baseline_mode?: "prior_period" | "custom";
      dimension_columns?: string[] | null;
      secondary_metrics?: string[] | null;
      max_dimensions?: number;
      top_k_drivers?: number;
      min_contribution_pct?: number;
    }
  ): Promise<RCAResponse> {
    return request<RCAResponse>(`/datasets/${datasetId}/rca/analyze`, {
      method: "POST",
      body: JSON.stringify(query),
    });
  },

  async analyzeAnomalyRCA(datasetId: string, anomalyId: string): Promise<RCAResponse> {
    return request<RCAResponse>(`/datasets/${datasetId}/rca/anomaly/${anomalyId}`);
  },
};
