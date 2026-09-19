"use client";

import React, { useState } from "react";
import { useAuth } from "../lib/auth-context";
import {
  Building2,
  Database,
  LogOut,
  Sparkles,
  User,
  CheckCircle2,
  AlertCircle,
  Plus,
} from "lucide-react";

export function Navbar() {
  const {
    user,
    organizations,
    currentOrg,
    setCurrentOrg,
    createOrg,
    currentDataset,
    logout,
  } = useAuth();

  const [showOrgModal, setShowOrgModal] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [creatingOrg, setCreatingOrg] = useState(false);

  async function handleCreateOrg(e: React.FormEvent) {
    e.preventDefault();

    if (!newOrgName.trim()) return;

    setCreatingOrg(true);

    try {
      await createOrg(newOrgName.trim());
      setNewOrgName("");
      setShowOrgModal(false);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setCreatingOrg(false);
    }
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white shadow-sm">
      <div className="mx-auto flex h-[72px] max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">

        {/* ===================================================== */}
        {/* BRAND */}
        {/* ===================================================== */}
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-200">
            <Sparkles className="h-5 w-5" />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xl font-bold tracking-tight text-slate-950">
              InsightForge
            </span>

            <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-xl font-bold text-transparent">
              AI
            </span>
          </div>
        </div>

        {/* ===================================================== */}
        {/* CENTER STATUS */}
        {/* ===================================================== */}
        <div className="hidden items-center gap-3 lg:flex">

          {/* Organization */}
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <Building2 className="h-4 w-4 text-indigo-600" />

            <select
              value={currentOrg?.id || ""}
              onChange={(e) => {
                if (e.target.value === "__create__") {
                  setShowOrgModal(true);
                } else {
                  const selected = organizations.find(
                    (o) => o.id === e.target.value
                  );

                  if (selected) {
                    setCurrentOrg(selected);
                  }
                }
              }}
              className="cursor-pointer bg-transparent text-xs font-semibold text-slate-800 outline-none"
            >
              {organizations.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}

              <option value="__create__">
                + New Organization
              </option>
            </select>
          </div>

          {/* Active dataset */}
          <div className="flex max-w-[310px] items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <Database className="h-4 w-4 shrink-0 text-indigo-600" />

            {currentDataset ? (
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="max-w-[150px] truncate text-xs font-semibold text-slate-800"
                  title={currentDataset.name}
                >
                  {currentDataset.name}
                </span>

                {currentDataset.is_cleaned ? (
                  <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                    <CheckCircle2 className="h-3 w-3" />
                    Cleaned
                  </span>
                ) : (
                  <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                    <AlertCircle className="h-3 w-3" />
                    Raw
                  </span>
                )}
              </div>
            ) : (
              <span className="text-xs text-slate-400">
                No dataset selected
              </span>
            )}
          </div>
        </div>

        {/* ===================================================== */}
        {/* USER */}
        {/* ===================================================== */}
        <div className="flex items-center gap-3">

          <div className="hidden text-right sm:block">
            <p className="text-xs font-bold text-slate-800">
              {user?.full_name || user?.email?.split("@")[0]}
            </p>

            <p className="mt-0.5 text-[11px] text-slate-500">
              {user?.email}
            </p>
          </div>

          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-600">
            <User className="h-4 w-4" />
          </div>

          <button
            onClick={() => logout()}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600"
            title="Sign Out"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>

      {/* ===================================================== */}
      {/* CREATE ORGANIZATION MODAL */}
      {/* ===================================================== */}
      {showOrgModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">

            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                <Plus className="h-5 w-5" />
              </div>

              <div>
                <h3 className="text-lg font-bold text-slate-950">
                  Create Organization
                </h3>

                <p className="text-xs text-slate-500">
                  Add a new workspace for your data.
                </p>
              </div>
            </div>

            <form
              onSubmit={handleCreateOrg}
              className="mt-6 space-y-4"
            >
              <div>
                <label className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-slate-600">
                  Organization Name
                </label>

                <input
                  type="text"
                  required
                  value={newOrgName}
                  onChange={(e) => setNewOrgName(e.target.value)}
                  placeholder="Acme Analytics"
                  className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowOrgModal(false)}
                  className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={creatingOrg}
                  className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {creatingOrg ? "Creating..." : "Create Organization"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </header>
  );
}