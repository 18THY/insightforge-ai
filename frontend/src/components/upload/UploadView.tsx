"use client";

import React, { useState, useRef } from "react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import {
  UploadCloud,
  FileSpreadsheet,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Info,
} from "lucide-react";

export function UploadView() {
  const { currentOrg, refreshDatasets, setCurrentDataset, setActiveStep } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelected(selectedFile: File) {
    const ext = selectedFile.name.split(".").pop()?.toLowerCase();
    if (ext !== "csv" && ext !== "xlsx") {
      setError("Only .csv and .xlsx files are supported.");
      return;
    }
    setError(null);
    setFile(selectedFile);
    if (!name) {
      const baseName = selectedFile.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
      setName(baseName.charAt(0).toUpperCase() + baseName.slice(1));
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Please select a CSV or XLSX file to upload.");
      return;
    }
    if (!currentOrg) {
      setError("No active organization found. Please select or create an organization.");
      return;
    }
    if (!name.trim()) {
      setError("Please provide a name for this dataset.");
      return;
    }

    setUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const uploaded = await api.uploadDataset(
        currentOrg.id,
        file,
        name.trim(),
        description.trim() || undefined
      );

      setSuccessMsg(`Dataset "${uploaded.name}" uploaded successfully!`);
      await refreshDatasets();
      setCurrentDataset(uploaded);

      // Transition to Profile tab
      setTimeout(() => {
        setActiveStep("profile");
      }, 1000);
    } catch (err) {
      setError((err as Error).message || "Failed to upload dataset.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Upload Dataset</h1>
        <p className="mt-1 text-sm text-slate-600">
          Upload raw CSV or Excel spreadsheets to target organization{" "}
          <span className="font-semibold text-slate-900">"{currentOrg?.name}"</span>.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold">Upload Failed</p>
            <p className="mt-0.5 text-xs text-rose-700">{error}</p>
          </div>
        </div>
      )}

      {successMsg && (
        <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-800">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold">Success</p>
            <p className="mt-0.5 text-xs text-emerald-700">
              {successMsg} Redirecting to 5D Data Profiler...
            </p>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Drag and Drop Box */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 text-center transition cursor-pointer ${
            isDragging
              ? "border-indigo-500 bg-indigo-50/50"
              : file
              ? "border-emerald-300 bg-emerald-50/20"
              : "border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50/50"
          }`}
        >
          <input
            type="file"
            ref={fileInputRef}
            accept=".csv,.xlsx"
            className="hidden"
            onChange={(e) => {
              if (e.target.files && e.target.files[0]) {
                handleFileSelected(e.target.files[0]);
              }
            }}
          />

          {file ? (
            <div className="flex flex-col items-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700 mb-3 shadow-inner">
                <FileSpreadsheet className="h-7 w-7" />
              </div>
              <p className="text-base font-bold text-slate-900">{file.name}</p>
              <p className="text-xs text-slate-500 mt-1">
                {(file.size / (1024 * 1024)).toFixed(2)} MB • Click or drag to replace
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 mb-3">
                <UploadCloud className="h-7 w-7" />
              </div>
              <p className="text-base font-semibold text-slate-800">
                Click to browse or drag and drop a file
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Supports Comma-Separated Values (.csv) or Microsoft Excel (.xlsx) up to 100 MB
              </p>
            </div>
          )}
        </div>

        {/* Dataset Metadata Fields */}
        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Dataset Name <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., E-Commerce Orders 2024"
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Description <span className="text-slate-400 lowercase font-normal">(optional)</span>
            </label>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Provide context regarding data source, ingestion frequency, or business unit..."
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
            />
          </div>
        </div>

        {/* Informational Box */}
        <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-600">
          <Info className="h-4 w-4 shrink-0 text-slate-400 mt-0.5" />
          <p>
            Upon upload, InsightForge AI will parse the file, compute row/column metrics, and immediately generate an immutable 5-Dimensional Data Quality score across Completeness, Uniqueness, Type Consistency, Date Validity, and Reasonableness.
          </p>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={uploading || !file}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-md shadow-indigo-600/20 transition hover:bg-indigo-700 disabled:opacity-50"
        >
          <span>{uploading ? "Ingesting & Computing Schema..." : "Upload & Analyze Dataset"}</span>
          <ArrowRight className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}
