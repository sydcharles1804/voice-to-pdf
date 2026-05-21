"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LatestSession {
  id: string;
  status: "active" | "completed" | "abandoned";
  fields_answered: number;
  fields_total: number | null;
  completed_at: string | null;
  created_at: string;
}

interface PDFItem {
  id: string;
  name: string;
  original_name: string;
  page_count: number | null;
  field_count: number | null;
  created_at: string;
  latest_session: LatestSession | null;
}

export interface PDFLibraryProps {
  authToken: string;
  onSessionStart: (sessionId: string, pdfName: string, fieldCount: number) => void;
  onSignOut: () => void;
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function fetchPDFs(token: string): Promise<PDFItem[]> {
  const res = await fetch(`${API_BASE}/pdfs/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load your forms");
  const body = await res.json();
  return body.data as PDFItem[];
}

async function createSession(token: string, pdfId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/sessions/`, {
    method: "POST",
    headers: {
      "Content-Type":  "application/json",
      Authorization:   `Bearer ${token}`,
    },
    body: JSON.stringify({ pdf_id: pdfId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? "Failed to start session");
  }
  const { data } = await res.json();
  return data.id as string;
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m    = Math.floor(diff / 60_000);
  const h    = Math.floor(diff / 3_600_000);
  const d    = Math.floor(diff / 86_400_000);
  if (m  <  1) return "just now";
  if (m  < 60) return `${m}m ago`;
  if (h  < 24) return `${h}h ago`;
  if (d  <  7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ session, fieldCount }: {
  session:    LatestSession | null;
  fieldCount: number | null;
}) {
  if (!session) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
        Not started
      </span>
    );
  }
  if (session.status === "completed") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" clipRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
          />
        </svg>
        Completed
      </span>
    );
  }
  if (session.status === "active") {
    const total = session.fields_total ?? fieldCount ?? 0;
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
        In progress · {session.fields_answered}/{total}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-400">
      Abandoned
    </span>
  );
}

function PDFCard({ pdf, authToken, onSessionStart }: {
  pdf:            PDFItem;
  authToken:      string;
  onSessionStart: PDFLibraryProps["onSessionStart"];
}) {
  const [starting, setStarting] = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const qc = useQueryClient();

  const lastActivity = pdf.latest_session
    ? pdf.latest_session.created_at
    : pdf.created_at;

  const btnLabel =
    pdf.latest_session?.status === "completed"  ? "Fill again"  :
    pdf.latest_session?.status === "active"     ? "Continue"    :
                                                  "Fill by voice";

  async function handleStart() {
    setError(null);
    setStarting(true);
    try {
      const sessionId = await createSession(authToken, pdf.id);
      await qc.invalidateQueries({ queryKey: ["pdfs"] });
      onSessionStart(sessionId, pdf.name, pdf.field_count ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setStarting(false);
    }
  }

  return (
    <div className="group bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-all flex flex-col overflow-hidden">
      {/* Thumbnail */}
      <div className="relative bg-gradient-to-br from-blue-50 to-indigo-100 h-36 flex items-center justify-center shrink-0">
        <svg
          className="w-16 h-16 text-blue-200"
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        {pdf.page_count && (
          <span className="absolute top-3 right-3 text-xs font-medium bg-white/80 text-gray-500 px-2 py-0.5 rounded-full backdrop-blur-sm">
            {pdf.page_count}p
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex flex-col flex-1 gap-3 p-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 truncate" title={pdf.name}>
            {pdf.name}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {pdf.field_count ?? "—"} fields · {formatRelative(lastActivity)}
          </p>
        </div>

        <StatusBadge session={pdf.latest_session} fieldCount={pdf.field_count} />

        {error && (
          <p className="text-xs text-red-600">{error}</p>
        )}

        <button
          onClick={handleStart}
          disabled={starting}
          className={[
            "mt-auto w-full text-sm font-medium rounded-xl py-2 transition-colors",
            starting
              ? "bg-blue-100 text-blue-400 cursor-not-allowed"
              : "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800",
          ].join(" ")}
        >
          {starting ? "Starting…" : btnLabel}
        </button>
      </div>
    </div>
  );
}

function PDFCardSkeleton() {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden animate-pulse">
      <div className="bg-gray-100 h-36" />
      <div className="p-4 flex flex-col gap-3">
        <div>
          <div className="h-4 bg-gray-100 rounded w-3/4" />
          <div className="h-3 bg-gray-100 rounded w-1/2 mt-1.5" />
        </div>
        <div className="h-5 bg-gray-100 rounded-full w-24" />
        <div className="h-9 bg-gray-100 rounded-xl mt-auto" />
      </div>
    </div>
  );
}

function UploadingCard() {
  return (
    <div className="bg-white rounded-2xl border border-blue-200 overflow-hidden">
      <div className="bg-blue-50 h-36 flex flex-col items-center justify-center gap-3">
        <div className="w-7 h-7 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs font-medium text-blue-500">Extracting fields…</p>
      </div>
      <div className="p-4 flex flex-col gap-3 animate-pulse">
        <div>
          <div className="h-4 bg-blue-50 rounded w-2/3" />
          <div className="h-3 bg-blue-50 rounded w-1/3 mt-1.5" />
        </div>
        <div className="h-5 bg-blue-50 rounded-full w-20" />
        <div className="h-9 bg-blue-50 rounded-xl" />
      </div>
    </div>
  );
}

function EmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="col-span-full flex flex-col items-center justify-center py-24 gap-4">
      <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center">
        <svg className="w-8 h-8 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
      </div>
      <div className="text-center">
        <p className="text-sm font-semibold text-gray-700">No forms yet</p>
        <p className="text-xs text-gray-400 mt-1">Upload a fillable PDF to get started</p>
      </div>
      <button
        onClick={onUpload}
        className="text-sm font-medium text-blue-600 hover:text-blue-700 transition-colors"
      >
        Upload your first form →
      </button>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function PDFLibrary({ authToken, onSessionStart, onSignOut }: PDFLibraryProps) {
  const fileInputRef               = useRef<HTMLInputElement>(null);
  const [uploading, setUploading]  = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const qc = useQueryClient();

  const { data: pdfs, isLoading, isError } = useQuery({
    queryKey: ["pdfs"],
    queryFn:  () => fetchPDFs(authToken),
  });

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadError(null);
    setUploading(true);
    if (fileInputRef.current) fileInputRef.current.value = "";

    try {
      // 1. Upload PDF (field extraction takes 2–5 s for complex forms)
      const formData = new FormData();
      formData.append("file", file);
      const uploadRes = await fetch(`${API_BASE}/pdfs/`, {
        method:  "POST",
        headers: { Authorization: `Bearer ${authToken}` },
        body:    formData,
      });
      if (!uploadRes.ok) {
        const body = await uploadRes.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Upload failed (${uploadRes.status})`);
      }
      const { data: uploadData } = await uploadRes.json();

      // 2. Create session and navigate immediately
      const sessionId = await createSession(authToken, uploadData.pdf_id);
      await qc.invalidateQueries({ queryKey: ["pdfs"] });
      onSessionStart(sessionId, file.name.replace(/\.pdf$/i, ""), uploadData.field_count ?? 0);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
    }
  }

  const showEmpty = !isLoading && !isError && !uploading && (pdfs?.length ?? 0) === 0;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-gray-100 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-base font-bold text-gray-900">Voice to PDF</h1>
            {!isLoading && !isError && (pdfs?.length ?? 0) > 0 && (
              <p className="text-xs text-gray-400 mt-0.5">
                {pdfs!.length} form{pdfs!.length !== 1 ? "s" : ""}
              </p>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
              className={[
                "flex items-center gap-1.5 text-sm font-medium px-4 py-2 rounded-xl transition-colors",
                uploading
                  ? "bg-blue-100 text-blue-400 cursor-not-allowed"
                  : "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800",
              ].join(" ")}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              {uploading ? "Uploading…" : "Upload PDF"}
            </button>

            <button
              onClick={onSignOut}
              className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Grid */}
      <main className="max-w-5xl mx-auto px-6 py-8">
        {uploadError && (
          <div className="mb-6 text-sm text-red-600 bg-red-50 rounded-xl px-4 py-3 flex items-start gap-2">
            <svg className="w-4 h-4 mt-0.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" clipRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              />
            </svg>
            {uploadError}
          </div>
        )}

        {isError && (
          <div className="text-center py-16">
            <p className="text-sm text-gray-400">Failed to load your forms.</p>
            <button
              onClick={() => qc.invalidateQueries({ queryKey: ["pdfs"] })}
              className="mt-2 text-sm text-blue-600 hover:underline"
            >
              Try again
            </button>
          </div>
        )}

        {!isError && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Uploading placeholder — always first */}
            {uploading && <UploadingCard />}

            {/* Loading skeletons */}
            {isLoading && [0, 1, 2].map(i => <PDFCardSkeleton key={i} />)}

            {/* Empty state */}
            {showEmpty && <EmptyState onUpload={() => fileInputRef.current?.click()} />}

            {/* PDF cards */}
            {pdfs?.map(pdf => (
              <PDFCard
                key={pdf.id}
                pdf={pdf}
                authToken={authToken}
                onSessionStart={onSessionStart}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
