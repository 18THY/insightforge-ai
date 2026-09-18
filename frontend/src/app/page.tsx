"use client";

import { useEffect, useState } from "react";

type BackendStatus = "checking" | "online" | "offline";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_URL}/health`)
      .then((res) => (res.ok ? setStatusIfActive("online") : setStatusIfActive("offline")))
      .catch(() => setStatusIfActive("offline"));

    function setStatusIfActive(next: BackendStatus) {
      if (!cancelled) setStatus(next);
    }

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-start justify-center gap-4 px-6">
      <h1 className="text-3xl font-semibold tracking-tight">InsightForge AI</h1>
      <p className="text-slate-600">
        Project foundation is running. Application features will be added
        incrementally in later phases.
      </p>
      <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm">
        <span
          className={
            "h-2.5 w-2.5 rounded-full " +
            (status === "online"
              ? "bg-green-500"
              : status === "offline"
                ? "bg-red-500"
                : "bg-amber-400")
          }
        />
        <span>
          Backend status:{" "}
          <span className="font-medium">
            {status === "checking" ? "checking…" : status}
          </span>
        </span>
      </div>
    </main>
  );
}
