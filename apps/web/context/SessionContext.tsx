"use client";

import { createContext, useContext, type ReactNode } from "react";

export interface SessionField {
  id:         string;
  name:       string;
  label:      string;
  pageNumber: number;
  coords: {
    x:      number | null;
    y:      number | null;
    width:  number | null;
    height: number | null;
  };
}

interface SessionContextValue {
  // ── Static config (set once at session start, never changes) ──────────────
  sessionId:   string;
  pdfId:       string;
  authToken:   string;
  apiBase:     string;

  // ── PDF data (from TanStack Query, stable after first load) ───────────────
  fields:      SessionField[];
  templateUrl: string | null;
  fieldCount:  number;
  pdfName:     string;

  // ── Live session cursor (updated by polling) ───────────────────────────────
  answeredNames:    Set<string>;
  skippedNames:     Set<string>;
  currentFieldName: string | null;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({
  value,
  children,
}: {
  value:    SessionContextValue;
  children: ReactNode;
}) {
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
