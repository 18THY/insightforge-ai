"use client";

import React from "react";
import { useAuth, WorkflowStep } from "../lib/auth-context";
import {
  LayoutDashboard,
  UploadCloud,
  FileCheck2,
  Wand2,
  BarChart3,
  AlertTriangle,
  TrendingUp,
  GitMerge,
} from "lucide-react";

interface StepConfig {
  id: WorkflowStep;
  label: string;
  sublabel: string;
  icon: React.ComponentType<{ className?: string }>;
  requiresDataset: boolean;
}

const STEPS: StepConfig[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    sublabel: "Overview & Datasets",
    icon: LayoutDashboard,
    requiresDataset: false,
  },
  {
    id: "upload",
    label: "Upload",
    sublabel: "CSV / XLSX",
    icon: UploadCloud,
    requiresDataset: false,
  },
  {
    id: "profile",
    label: "Profile",
    sublabel: "5D Quality Score",
    icon: FileCheck2,
    requiresDataset: true,
  },
  {
    id: "clean",
    label: "Cleaning",
    sublabel: "Rules & Imputation",
    icon: Wand2,
    requiresDataset: true,
  },
  {
    id: "analytics",
    label: "Analytics",
    sublabel: "KPIs & Trends",
    icon: BarChart3,
    requiresDataset: true,
  },
  {
    id: "anomalies",
    label: "Anomalies",
    sublabel: "Z-Score & Isolation",
    icon: AlertTriangle,
    requiresDataset: true,
  },
  {
    id: "forecasts",
    label: "Forecasts",
    sublabel: "95% Prediction Band",
    icon: TrendingUp,
    requiresDataset: true,
  },
  {
    id: "rca",
    label: "Root-Cause",
    sublabel: "Waterfall Drivers",
    icon: GitMerge,
    requiresDataset: true,
  },
];

export function StepNavigation() {
  const { activeStep, setActiveStep, currentDataset } = useAuth();

  return (
    <nav className="border-b border-slate-200 bg-white px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl overflow-x-auto py-2.5">
        <ol className="flex min-w-max items-center gap-1 sm:gap-2">
          {STEPS.map((step, idx) => {
            const Icon = step.icon;
            const isActive = activeStep === step.id;
            const isDisabled = step.requiresDataset && !currentDataset;

            return (
              <li key={step.id} className="flex items-center">
                <button
                  type="button"
                  disabled={isDisabled}
                  onClick={() => setActiveStep(step.id)}
                  title={isDisabled ? "Select or upload a dataset first" : step.label}
                  className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs transition ${
                    isActive
                      ? "bg-indigo-50 font-semibold text-indigo-700 shadow-sm ring-1 ring-indigo-200"
                      : isDisabled
                      ? "cursor-not-allowed text-slate-300"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  <div
                    className={`flex h-7 w-7 items-center justify-center rounded-md transition ${
                      isActive
                        ? "bg-indigo-600 text-white"
                        : isDisabled
                        ? "bg-slate-100 text-slate-300"
                        : "bg-slate-100 text-slate-600 group-hover:bg-slate-200"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-1">
                      <span className="font-semibold">{step.label}</span>
                    </div>
                    <p
                      className={`text-[10px] ${
                        isActive
                          ? "text-indigo-600"
                          : isDisabled
                          ? "text-slate-300"
                          : "text-slate-500"
                      }`}
                    >
                      {step.sublabel}
                    </p>
                  </div>
                </button>

                {idx < STEPS.length - 1 && (
                  <span className="mx-1 text-slate-300 font-light select-none">›</span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </nav>
  );
}
