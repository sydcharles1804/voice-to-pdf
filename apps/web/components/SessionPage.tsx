"use client";

import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { type SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useRef, useState } from "react";
import { VoiceCallButton } from "@/components/VoiceCallButton";
import { createClient } from "@/lib/supabase";

type Stage = "loading" | "auth" | "setup" | "session";
type UploadState = "idle" | "uploading" | "starting";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function SessionPage() {
  const supabase                          = createClient();
  const [stage, setStage]                 = useState<Stage>("loading");
  const [authToken, setAuthToken]         = useState<string | null>(null);
  const [sessionId, setSessionId]         = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [pdfName, setPdfName]             = useState<string | null>(null);
  const [fieldCount, setFieldCount]       = useState<number | null>(null);
  const [uploadState, setUploadState]     = useState<UploadState>("idle");
  const [error, setError]                 = useState<string | null>(null);
  const fileInputRef                      = useRef<HTMLInputElement>(null);

  // ── Auth listener ──────────────────────────────────────────────────────────
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.access_token) {
        setAuthToken(session.access_token);
        setStage("setup");
      } else {
        setStage("auth");
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (session?.access_token) {
          setAuthToken(session.access_token);
          setStage("setup");
        } else {
          setAuthToken(null);
          setStage("auth");
          setSessionId(null);
        }
      }
    );

    return () => subscription.unsubscribe();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Upload PDF → create session ────────────────────────────────────────────
  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !authToken) return;

    setError(null);
    setUploadState("uploading");

    try {
      // Step 1: upload the PDF
      const formData = new FormData();
      formData.append("file", file);

      const uploadRes = await fetch(`${API_BASE}/pdfs/`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${authToken}` },
        body: formData,
      });

      if (!uploadRes.ok) {
        const body = await uploadRes.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Upload failed (HTTP ${uploadRes.status})`);
      }

      const { data: uploadData } = await uploadRes.json();
      const pdfId: string = uploadData.pdf_id;

      setUploadState("starting");

      // Step 2: create the session
      const sessionRes = await fetch(`${API_BASE}/sessions/`, {
        method: "POST",
        headers: {
          "Content-Type":  "application/json",
          "Authorization": `Bearer ${authToken}`,
        },
        body: JSON.stringify({ pdf_id: pdfId }),
      });

      if (!sessionRes.ok) {
        const body = await sessionRes.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Session create failed (HTTP ${sessionRes.status})`);
      }

      const { data: sessionData } = await sessionRes.json();
      setSessionId(sessionData.id);
      setSessionStatus(sessionData.status);
      setPdfName(file.name.replace(/\.pdf$/i, ""));
      setFieldCount(uploadData.field_count);
      setStage("session");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setUploadState("idle");
      // Reset input so the same file can be re-selected if needed
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  // ── Sign out ───────────────────────────────────────────────────────────────
  async function handleSignOut() {
    await supabase.auth.signOut();
    setSessionId(null);
    setPdfName(null);
    setStage("auth");
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (stage === "loading") {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (stage === "auth") {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2 text-center">
            Voice to PDF
          </h1>
          <p className="text-sm text-gray-500 text-center mb-6">
            Sign in to start filling forms by voice
          </p>
          <Auth
            supabaseClient={supabase as SupabaseClient}
            appearance={{ theme: ThemeSupa }}
            providers={[]}
            redirectTo={typeof window !== "undefined" ? window.location.href : undefined}
          />
        </div>
      </div>
    );
  }

  if (stage === "setup") {
    const busy = uploadState !== "idle";
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border border-gray-100 p-8 flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">Voice to PDF</h1>
            <button
              onClick={handleSignOut}
              className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              Sign out
            </button>
          </div>

          {/* Drop zone */}
          <button
            type="button"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
            className={[
              "relative flex flex-col items-center justify-center gap-3",
              "w-full rounded-2xl border-2 border-dashed py-12 px-6 transition-colors",
              busy
                ? "border-blue-300 bg-blue-50 cursor-not-allowed"
                : "border-gray-200 hover:border-blue-400 hover:bg-blue-50 cursor-pointer",
            ].join(" ")}
          >
            {busy ? (
              <>
                <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                <p className="text-sm font-medium text-blue-600">
                  {uploadState === "uploading" ? "Uploading PDF…" : "Starting session…"}
                </p>
              </>
            ) : (
              <>
                <svg className="w-10 h-10 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                <div className="text-center">
                  <p className="text-sm font-medium text-gray-700">Upload a PDF form</p>
                  <p className="text-xs text-gray-400 mt-1">Click to browse · max 25 MB · fillable fields required</p>
                </div>
              </>
            )}
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={handleFileChange}
          />

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2">
              {error}
            </p>
          )}
        </div>
      </div>
    );
  }

  // stage === "session"
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border border-gray-100 p-8 flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {pdfName ?? "Form Session"}
            </h1>
            {fieldCount !== null && (
              <p className="text-xs text-gray-400 mt-0.5">
                {fieldCount} fillable field{fieldCount !== 1 ? "s" : ""} detected
              </p>
            )}
          </div>
          <button
            onClick={() => { setStage("setup"); setSessionId(null); setPdfName(null); }}
            className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            New form
          </button>
        </div>

        <div className="w-24 h-24 rounded-full bg-blue-50 flex items-center justify-center mx-auto">
          <svg className="w-10 h-10 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
            />
          </svg>
        </div>

        <VoiceCallButton
          sessionId={sessionId!}
          apiBase={API_BASE}
          authToken={authToken!}
        />

        {sessionStatus && (
          <p className="text-xs text-center text-gray-400">
            Session status: <span className="font-medium text-gray-600">{sessionStatus}</span>
          </p>
        )}
      </div>
    </div>
  );
}
