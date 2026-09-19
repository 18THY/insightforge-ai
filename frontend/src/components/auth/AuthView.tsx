"use client";

import React, { useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { Sparkles, ArrowRight, ShieldCheck, Database, LineChart, GitMerge } from "lucide-react";

export function AuthView() {
  const { login, register } = useAuth();
  const [isRegister, setIsRegister] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (isRegister) {
        if (password.length < 8) {
          throw new Error("Password must be at least 8 characters long.");
        }
        await register(email.trim(), password, fullName.trim() || undefined);
      } else {
        await login(email.trim(), password);
      }
    } catch (err) {
      setError((err as Error).message || "Authentication failed. Please check your credentials.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Left Feature Showcase Banner */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-slate-900 p-12 text-white">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-500/30">
              <Sparkles className="h-6 w-6" />
            </div>
            <span className="text-2xl font-bold tracking-tight">
              InsightForge <span className="text-indigo-400">AI</span>
            </span>
          </div>
          <p className="mt-4 text-lg text-slate-300">
            Enterprise-grade Business Intelligence & Predictive Analytics Platform.
          </p>
        </div>

        {/* Value Props */}
        <div className="space-y-6">
          <div className="flex items-start gap-4">
            <div className="rounded-lg bg-indigo-950 p-2.5 text-indigo-400">
              <Database className="h-5 w-5" />
            </div>
            <div>
              <h4 className="font-semibold text-white">5-Dimensional Data Profiling & Cleaning</h4>
              <p className="text-sm text-slate-400">
                Transparent 0–100 quality scoring across completeness, uniqueness, type consistency, date validity, and reasonableness.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="rounded-lg bg-indigo-950 p-2.5 text-indigo-400">
              <LineChart className="h-5 w-5" />
            </div>
            <div>
              <h4 className="font-semibold text-white">Deterministic ML & Forecasting</h4>
              <p className="text-sm text-slate-400">
                Rolling Z-Score & Isolation Forest anomaly detection paired with OLS calendar-trend forecasts and 95% prediction intervals.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="rounded-lg bg-indigo-950 p-2.5 text-indigo-400">
              <GitMerge className="h-5 w-5" />
            </div>
            <div>
              <h4 className="font-semibold text-white">Waterfall Root-Cause Analysis</h4>
              <p className="text-sm text-slate-400">
                Mathematical driver decomposition reconciling 100% of metric variance with statistical z-score significance and elasticity.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <span>Multi-tenant tenant isolation with role-based access control</span>
        </div>
      </div>

      {/* Right Login / Register Form */}
      <div className="flex flex-1 items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-md space-y-8">
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600 text-white lg:hidden">
              <Sparkles className="h-6 w-6" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              {isRegister ? "Create your account" : "Welcome back"}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              {isRegister
                ? "Sign up to start profiling and analyzing your datasets"
                : "Enter your credentials to access your workspaces"}
            </p>
          </div>

          {/* Form Tabs */}
          <div className="grid grid-cols-2 rounded-lg bg-slate-100 p-1 text-sm font-medium">
            <button
              type="button"
              onClick={() => {
                setIsRegister(false);
                setError(null);
              }}
              className={`rounded-md py-2 transition ${
                !isRegister ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setIsRegister(true);
                setError(null);
              }}
              className={`rounded-md py-2 transition ${
                isRegister ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Create Account
            </button>
          </div>

          {/* Error Alert */}
          {error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              <p className="font-semibold">Authentication Error</p>
              <p className="mt-1 text-xs">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                  Full Name
                </label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Jane Doe"
                  className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Email Address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="analyst@company.com"
                className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                minLength={8}
                className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
              />
              {isRegister && (
                <p className="mt-1 text-[11px] text-slate-500">Minimum 8 characters required</p>
              )}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2 disabled:opacity-50"
            >
              <span>{submitting ? "Processing..." : isRegister ? "Create Account" : "Sign In"}</span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
