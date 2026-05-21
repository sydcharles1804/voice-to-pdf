"use client";

import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { type SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useState } from "react";
import { PDFLibrary } from "@/components/PDFLibrary";
import { VoiceCallButton } from "@/components/VoiceCallButton";
import { createClient } from "@/lib/supabase";

type Stage = "loading" | "auth" | "library" | "session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function SessionPage() {
  const supabase = createClient();

  const [stage,         setStage]         = useState<Stage>("loading");
  const [authToken,     setAuthToken]     = useState<string | null>(null);
  const [sessionId,     setSessionId]     = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [pdfName,       setPdfName]       = useState<string | null>(null);
  const [fieldCount,    setFieldCount]    = useState<number | null>(null);

  // ── Auth listener ──────────────────────────────────────────────────────────
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.access_token) {
        setAuthToken(session.access_token);
        setStage("library");
      } else {
        setStage("auth");
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (session?.access_token) {
          setAuthToken(session.access_token);
          setStage("library");
        } else {
          setAuthToken(null);
          setStage("auth");
          setSessionId(null);
        }
      },
    );

    return () => subscription.unsubscribe();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Called by PDFLibrary when a session is ready ───────────────────────────
  function handleSessionStart(sid: string, name: string, count: number) {
    setSessionId(sid);
    setPdfName(name);
    setFieldCount(count);
    setSessionStatus("active");
    setStage("session");
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

  if (stage === "library") {
    return (
      <PDFLibrary
        authToken={authToken!}
        onSessionStart={handleSessionStart}
        onSignOut={handleSignOut}
      />
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
                {fieldCount} fillable field{fieldCount !== 1 ? "s" : ""}
              </p>
            )}
          </div>
          <button
            onClick={() => { setStage("library"); setSessionId(null); setPdfName(null); }}
            className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            ← Library
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
            Session status:{" "}
            <span className="font-medium text-gray-600">{sessionStatus}</span>
          </p>
        )}
      </div>
    </div>
  );
}
