"use client";

import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { type SupabaseClient } from "@supabase/supabase-js";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { PDFLibrary } from "@/components/PDFLibrary";
import { SessionProvider } from "@/context/SessionContext";
import { SessionView } from "@/components/session/SessionView";
import { createClient } from "@/lib/supabase";
import { useSessionStore } from "@/store/sessionStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Stage = "loading" | "auth" | "library" | "session";

// ── SessionPage ───────────────────────────────────────────────────────────────

export function SessionPage() {
  const supabase = createClient();

  const [stage,      setStage]      = useState<Stage>("loading");
  const [authToken,  setAuthToken]  = useState<string | null>(null);
  const [sessionId,  setSessionId]  = useState<string | null>(null);
  const [pdfId,      setPdfId]      = useState<string | null>(null);
  const [pdfName,    setPdfName]    = useState<string | null>(null);
  const [fieldCount, setFieldCount] = useState<number | null>(null);

  const { isCallActive, reset: resetCall } = useSessionStore();

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
    resetCall();
    setSessionId(sid);
    setPdfName(name);
    setFieldCount(count);
    setPdfId(pid);
    setStage("session");
  }

  function handleBackToLibrary() {
    resetCall();
    setSessionId(null); setPdfName(null); setPdfId(null);
    setStage("library");
  }

  async function handleSignOut() {
    resetCall();
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

  // ── Render: session ───────────────────────────────────────────────────────
  return (
    <SessionProvider value={{
      sessionId:        sessionId!,
      pdfId:            pdfId!,
      authToken:        authToken!,
      apiBase:          API_BASE,
      fields:           pdfData?.fields ?? [],
      templateUrl:      pdfData?.template_url ?? null,
      fieldCount:       fieldCount ?? 0,
      pdfName:          pdfName ?? "",
      answeredNames,
      skippedNames,
      currentFieldName,
    }}>
      <SessionView onBack={handleBackToLibrary} />
    </SessionProvider>
  );
}
