"use client";

import React from "react";
import { AuthProvider, useAuth } from "../lib/auth-context";
import { Navbar } from "../components/Navbar";
import { StepNavigation } from "../components/StepNavigation";
import { AuthView } from "../components/auth/AuthView";
import { DashboardView } from "../components/dashboard/DashboardView";
import { UploadView } from "../components/upload/UploadView";
import { ProfileView } from "../components/profile/ProfileView";
import { CleaningView } from "../components/cleaning/CleaningView";
import { AnalyticsView } from "../components/analytics/AnalyticsView";
import { AnomaliesView } from "../components/ml/AnomaliesView";
import { ForecastsView } from "../components/ml/ForecastsView";
import { RCAView } from "../components/rca/RCAView";

function MainWorkspace() {
  const { user, isLoading, activeStep } = useAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent mb-3" />
          <p className="text-xs font-semibold text-slate-500 tracking-wide uppercase">
            Loading InsightForge AI Workspace...
          </p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <AuthView />;
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <Navbar />
      <StepNavigation />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        {activeStep === "dashboard" && <DashboardView />}
        {activeStep === "upload" && <UploadView />}
        {activeStep === "profile" && <ProfileView />}
        {activeStep === "clean" && <CleaningView />}
        {activeStep === "analytics" && <AnalyticsView />}
        {activeStep === "anomalies" && <AnomaliesView />}
        {activeStep === "forecasts" && <ForecastsView />}
        {activeStep === "rca" && <RCAView />}
      </main>
    </div>
  );
}

export default function Home() {
  return (
    <AuthProvider>
      <MainWorkspace />
    </AuthProvider>
  );
}
