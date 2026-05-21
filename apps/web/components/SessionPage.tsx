"use client";

import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { type SupabaseClient } from "@supabase/supabase-js";
import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { PDFLibrary } from "@/components/PDFLibrary";
import { VoiceCallButton } from "@/components/VoiceCallButton";
import { createClient } from "@/lib/supabase";
import { useRetellCall } from "@/hooks/useRetellCall";

// Dynamic import with SSR disabled — pdfjs uses browser-only APIs (canvas).
const PDFViewer = dynamic(
  () => import("@/components/PDFViewer").then(m => m.PDFViewer),
  { ssr: false, loading: () => <PDFViewerPlaceholder /> },
);

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Stage = "loading" | "auth" | "library" | "session";

// ── Placeholder shown while PDFViewer JS bundle loads ─────────────────────────

function PDFViewerPlaceholder() {
  return (
    <div className="w-full h-full bg-gray-100 flex flex-col items-center justify-center gap-3">
      <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      <p className="text-xs text-gray-400">Loading viewer…</p>
    </div>
  );
}

// ── SessionPage ───────────────────────────────────────────────────────────────

export function SessionPage() {
  const supabase = createClient();

  const [stage,      setStage]      = useState<Stage>("loading");
  const [authToken,  setAuthToken]  = useState<string | null>(null);
  const [sessionId,  setSessionId]  = useState<string | null>(null);
  const [pdfId,      setPdfId]      = useState<string | null>(null);
  const [pdfName,    setPdfName]    = useState<string | null>(null);
  const [fieldCount, setFieldCount] = useState<number | null>(null);

  // ── Retell call state — lifted so SessionPage controls polling ─────────────
  const { startCall, stopCall, isCallActive, agentMode, transcript, error: callError } =
    useRetellCall({ apiBase: API_BASE, authToken: authToken ?? "" });

  // ── Auth listener ──────────────────────────────────────────────────────────
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.access_token) { setAuthToken(session.access_token); setStage("library"); }
      else                        setStage("auth");
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      if (session?.access_token) { setAuthToken(session.access_token); setStage("library"); }
      else { setAuthToken(null); setSessionId(null); setStage("auth"); }
    });

    return () => subscription.unsubscribe();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── PDF data (fetched once when session starts) ────────────────────────────
  const { data: pdfData } = useQuery({
    queryKey: ["pdf", pdfId],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/pdfs/${pdfId}`, {
        headers: { Authorization: `Bearer ${authToken!}` },
      });
      if (!res.ok) throw new Error("Failed to fetch PDF");
      const body = await res.json();
      return body.data as {
        id: string;
        name: string;
        fields: Array<{
          id: string; name: string; label: string;
          pageNumber: number;
          coords: { x: number | null; y: number | null; width: number | null; height: number | null };
        }>;
        template_url: string | null;
      };
    },
    enabled:   stage === "session" && !!pdfId && !!authToken,
    staleTime: Infinity,
  });

  // ── Session state (polled every 2 s during call, 10 s otherwise) ──────────
  const { data: sessionDetail } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${authToken!}` },
      });
      if (!res.ok) throw new Error("Failed to fetch session");
      const body = await res.json();
      return body.data as {
        session: { skipped_fields: string[] };
        answers: Array<{ field_name: string }>;
      };
    },
    enabled:         stage === "session" && !!sessionId && !!authToken,
    refetchInterval: isCallActive ? 2_000 : 10_000,
  });

  // ── Derive which field is currently being asked ────────────────────────────
  const answeredNames = useMemo(
    () => new Set((sessionDetail?.answers ?? []).map(a => a.field_name)),
    [sessionDetail],
  );
  const skippedNames = useMemo(
    () => new Set(sessionDetail?.session?.skipped_fields ?? []),
    [sessionDetail],
  );
  const currentFieldName = useMemo(() => {
    const fields = pdfData?.fields ?? [];
    return fields.find(f => !answeredNames.has(f.name) && !skippedNames.has(f.name))?.name ?? null;
  }, [pdfData, answeredNames, skippedNames]);

  // ── Callbacks ──────────────────────────────────────────────────────────────
  function handleSessionStart(sid: string, name: string, count: number, pid: string) {
    setSessionId(sid);
    setPdfName(name);
    setFieldCount(count);
    setPdfId(pid);
    setStage("session");
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    setSessionId(null); setPdfName(null); setPdfId(null);
    setStage("auth");
  }

  // ── Render: loading ────────────────────────────────────────────────────────
  if (stage === "loading") {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // ── Render: auth ───────────────────────────────────────────────────────────
  if (stage === "auth") {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2 text-center">Voice to PDF</h1>
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

  // ── Render: library ────────────────────────────────────────────────────────
  if (stage === "library") {
    return (
      <PDFLibrary
        authToken={authToken!}
        onSessionStart={handleSessionStart}
        onSignOut={handleSignOut}
      />
    );
  }

  // ── Render: session (split layout) ─────────────────────────────────────────
  const fields = pdfData?.fields ?? [];
  const templateUrl = pdfData?.template_url ?? null;

  return (
    <div className="flex flex-col h-screen bg-gray-50 overflow-hidden">
      {/* ── Header ── */}
      <header className="shrink-0 bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-base font-bold text-gray-900 truncate">
            {pdfName ?? "Form Session"}
          </h1>
          {fieldCount !== null && (
            <p className="text-xs text-gray-400">
              {answeredNames.size} / {fieldCount} fields answered
            </p>
          )}
        </div>
        <button
          onClick={() => { setStage("library"); setSessionId(null); setPdfName(null); }}
          className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
        >
          ← Library
        </button>
      </header>

      {/* ── Body (PDF left | controls right) ── */}
      <div className="flex flex-col lg:flex-row flex-1 min-h-0">

        {/* PDF Viewer panel */}
        <div className="h-[45vh] lg:h-full lg:flex-1 border-b lg:border-b-0 lg:border-r border-gray-200">
          {templateUrl ? (
            <PDFViewer
              pdfUrl={templateUrl}
              fields={fields}
              answeredNames={answeredNames}
              skippedNames={skippedNames}
              currentFieldName={currentFieldName}
            />
          ) : (
            <PDFViewerPlaceholder />
          )}
        </div>

        {/* Voice controls panel */}
        <div className="lg:w-80 xl:w-96 shrink-0 flex flex-col items-center justify-start gap-6 p-6 overflow-y-auto">
          {/* Mic icon */}
          <div className={[
            "w-20 h-20 rounded-full flex items-center justify-center transition-colors",
            isCallActive ? "bg-blue-100" : "bg-gray-100",
          ].join(" ")}>
            <svg
              className={`w-9 h-9 ${isCallActive ? "text-blue-600" : "text-gray-400"}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
          </div>

          {/* Current field hint */}
          {currentFieldName && isCallActive && (() => {
            const cf = fields.find(f => f.name === currentFieldName);
            return cf ? (
              <div className="w-full rounded-xl bg-blue-50 border border-blue-100 px-4 py-3 text-center">
                <p className="text-xs text-blue-400 font-medium uppercase tracking-wide">Now asking</p>
                <p className="text-sm font-semibold text-blue-700 mt-0.5">
                  {cf.label || cf.name}
                </p>
              </div>
            ) : null;
          })()}

          <VoiceCallButton
            sessionId={sessionId!}
            isCallActive={isCallActive}
            agentMode={agentMode}
            transcript={transcript}
            error={callError}
            onStart={() => startCall(sessionId!)}
            onStop={stopCall}
          />
        </div>
      </div>
    </div>
  );
}
