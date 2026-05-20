"use client";

import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { type SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useRef, useState } from "react";
import { VoiceCallButton } from "@/components/VoiceCallButton";
import { createClient } from "@/lib/supabase";

type Stage = "loading" | "auth" | "setup" | "session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function SessionPage() {
  const supabase                          = createClient();
  const [stage, setStage]                 = useState<Stage>("loading");
  const [authToken, setAuthToken]         = useState<string | null>(null);
  const [pdfId, setPdfId]                 = useState("");
  const [sessionId, setSessionId]         = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [creating, setCreating]           = useState(false);
  const [error, setError]                 = useState<string | null>(null);
  const pdfInputRef                       = useRef<HTMLInputElement>(null);

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

  // ── Create session ─────────────────────────────────────────────────────────
  async function handleStartSession() {
    const id = pdfId.trim();
    if (!id || !authToken) return;

    setCreating(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/sessions/`, {
        method: "POST",
        headers: {
          "Content-Type":  "application/json",
          "Authorization": `Bearer ${authToken}`,
        },
        body: JSON.stringify({ pdf_id: id }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }

      const { data } = await res.json();
      setSessionId(data.id);
      setSessionStatus(data.status);
      setStage("session");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setCreating(false);
    }
  }

  // ── Sign out ───────────────────────────────────────────────────────────────
  async function handleSignOut() {
    await supabase.auth.signOut();
    setSessionId(null);
    setPdfId("");
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
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border border-gray-100 p-8 flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">Start a Session</h1>
            <button
              onClick={handleSignOut}
              className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              Sign out
            </button>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-gray-700">PDF ID</label>
            <input
              ref={pdfInputRef}
              type="text"
              value={pdfId}
              onChange={(e) => setPdfId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleStartSession()}
              placeholder="Paste a PDF ID from your uploads"
              className="px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="text-xs text-gray-400">
              Upload a PDF first via <code className="bg-gray-100 px-1 rounded">POST /pdfs</code>,
              then paste its ID here.
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2">
              {error}
            </p>
          )}

          <button
            onClick={handleStartSession}
            disabled={creating || !pdfId.trim()}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-semibold rounded-xl transition-colors"
          >
            {creating ? "Creating session…" : "Start Session"}
          </button>
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
            <h1 className="text-2xl font-bold text-gray-900">Form Session</h1>
            <p className="text-xs text-gray-400 mt-0.5 font-mono truncate">
              {sessionId}
            </p>
          </div>
          <button
            onClick={() => { setStage("setup"); setSessionId(null); setPdfId(""); }}
            className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            New session
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
