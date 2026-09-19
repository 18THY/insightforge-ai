"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { api, loadStoredTokens, setAuthTokens } from "./api";
import { DatasetResponse, OrganizationResponse, UserResponse } from "./types";

export type WorkflowStep =
  | "dashboard"
  | "upload"
  | "profile"
  | "clean"
  | "analytics"
  | "anomalies"
  | "forecasts"
  | "rca";

interface AuthContextType {
  user: UserResponse | null;
  isLoading: boolean;
  login: (email: string, pass: string) => Promise<void>;
  register: (email: string, pass: string, name?: string) => Promise<void>;
  logout: () => Promise<void>;

  organizations: OrganizationResponse[];
  currentOrg: OrganizationResponse | null;
  setCurrentOrg: (org: OrganizationResponse | null) => void;
  createOrg: (name: string) => Promise<OrganizationResponse>;
  refreshOrgs: () => Promise<void>;

  datasets: DatasetResponse[];
  currentDataset: DatasetResponse | null;
  setCurrentDataset: (dataset: DatasetResponse | null) => void;
  refreshDatasets: () => Promise<void>;

  activeStep: WorkflowStep;
  setActiveStep: (step: WorkflowStep) => void;
  targetAnomalyId: string | null;
  setTargetAnomalyId: (id: string | null) => void;
  navigateToRCAWithAnomaly: (anomalyId: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const [organizations, setOrganizations] = useState<OrganizationResponse[]>([]);
  const [currentOrg, setCurrentOrg] = useState<OrganizationResponse | null>(null);

  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [currentDataset, setCurrentDataset] = useState<DatasetResponse | null>(null);

  const [activeStep, setActiveStep] = useState<WorkflowStep>("dashboard");
  const [targetAnomalyId, setTargetAnomalyId] = useState<string | null>(null);

  // Initialize Auth on mount
  useEffect(() => {
    async function initAuth() {
      const { accessToken } = loadStoredTokens();
      if (!accessToken) {
        setIsLoading(false);
        return;
      }
      try {
        const me = await api.getMe();
        setUser(me);
        const orgs = await api.listOrgs();
        setOrganizations(orgs);
        if (orgs.length > 0) {
          setCurrentOrg(orgs[0]);
        }
      } catch (err) {
        console.error("Auth init failed:", err);
        setAuthTokens(null, null);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    }

    initAuth();
  }, []);

  // Fetch datasets whenever currentOrg changes
  useEffect(() => {
    if (currentOrg) {
      refreshDatasets();
    } else {
      setDatasets([]);
      setCurrentDataset(null);
    }
  }, [currentOrg?.id]);

  async function refreshOrgs() {
    try {
      const orgs = await api.listOrgs();
      setOrganizations(orgs);
      if (orgs.length > 0 && (!currentOrg || !orgs.find((o) => o.id === currentOrg.id))) {
        setCurrentOrg(orgs[0]);
      }
    } catch (err) {
      console.error("Failed to refresh orgs:", err);
    }
  }

  async function refreshDatasets() {
    if (!currentOrg) return;
    try {
      const res = await api.listDatasets(currentOrg.id);
      setDatasets(res.items);
      // Keep currentDataset updated if it exists
      if (currentDataset) {
        const updated = res.items.find((d) => d.id === currentDataset.id);
        if (updated) {
          setCurrentDataset(updated);
        }
      } else if (res.items.length > 0) {
        setCurrentDataset(res.items[0]);
      }
    } catch (err) {
      console.error("Failed to refresh datasets:", err);
    }
  }

  async function login(email: string, pass: string) {
    setIsLoading(true);
    try {
      await api.login(email, pass);
      const me = await api.getMe();
      setUser(me);
      let orgs = await api.listOrgs();
      if (orgs.length === 0) {
        // Auto-create initial default workspace
        const newOrg = await api.createOrg(`${me.full_name || me.email.split("@")[0]}'s Org`);
        orgs = [newOrg];
      }
      setOrganizations(orgs);
      setCurrentOrg(orgs[0]);
      setActiveStep("dashboard");
    } finally {
      setIsLoading(false);
    }
  }

  async function register(email: string, pass: string, name?: string) {
    setIsLoading(true);
    try {
      await api.register(email, pass, name);
      await login(email, pass);
    } finally {
      setIsLoading(false);
    }
  }

  async function logout() {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setOrganizations([]);
      setCurrentOrg(null);
      setDatasets([]);
      setCurrentDataset(null);
      setActiveStep("dashboard");
      setTargetAnomalyId(null);
    }
  }

  async function createOrg(name: string): Promise<OrganizationResponse> {
    const newOrg = await api.createOrg(name);
    setOrganizations((prev) => [...prev, newOrg]);
    setCurrentOrg(newOrg);
    return newOrg;
  }

  function navigateToRCAWithAnomaly(anomalyId: string) {
    setTargetAnomalyId(anomalyId);
    setActiveStep("rca");
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        register,
        logout,
        organizations,
        currentOrg,
        setCurrentOrg,
        createOrg,
        refreshOrgs,
        datasets,
        currentDataset,
        setCurrentDataset,
        refreshDatasets,
        activeStep,
        setActiveStep,
        targetAnomalyId,
        setTargetAnomalyId,
        navigateToRCAWithAnomaly,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
