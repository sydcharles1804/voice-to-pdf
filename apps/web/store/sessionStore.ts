"use client";

import { create } from "zustand";
import { RetellWebClient } from "retell-client-js-sdk";

export type AgentMode = "idle" | "listening" | "speaking";

export interface TranscriptTurn {
  role:    "agent" | "user";
  content: string;
}

// The Retell client lives outside the store so Zustand never tries to
// serialize a WebRTC object.  All state that drives the UI lives in the store.
let _retellClient: RetellWebClient | null = null;

interface SessionStore {
  // ── Call state ────────────────────────────────────────────────────────────
  isCallActive: boolean;
  agentMode:    AgentMode;
  transcript:   TranscriptTurn[];
  error:        string | null;

  // ── UI state ──────────────────────────────────────────────────────────────
  activePanel: "pdf" | "transcript";

  // ── Actions ───────────────────────────────────────────────────────────────
  startCall:       (sessionId: string, apiBase: string, authToken: string) => Promise<void>;
  stopCall:        () => void;
  setActivePanel:  (panel: "pdf" | "transcript") => void;
  clearError:      () => void;
  clearTranscript: () => void;
  reset:           () => void;
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  isCallActive: false,
  agentMode:    "idle",
  transcript:   [],
  error:        null,
  activePanel:  "pdf",

  startCall: async (sessionId, apiBase, authToken) => {
    set({ error: null });

    // ── 1. Exchange sessionId for a Retell access token ───────────────────
    let accessToken: string;
    try {
      const res = await fetch(`${apiBase}/sessions/${sessionId}/start-call`, {
        method:  "POST",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const { data } = await res.json();
      accessToken = data.access_token;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Failed to start call" });
      return;
    }

    // ── 2. Build client and wire listeners BEFORE startCall() ─────────────
    const client = new RetellWebClient();
    _retellClient = client;

    client.on("call_started",        () => set({ isCallActive: true,  agentMode: "listening" }));
    client.on("call_ended",          () => set({ isCallActive: false, agentMode: "idle",      _retellClient: null } as any));
    client.on("agent_start_talking", () => set({ agentMode: "speaking"  }));
    client.on("agent_stop_talking",  () => set({ agentMode: "listening" }));

    client.on("update", (update: any) => {
      if (Array.isArray(update.transcript)) {
        set({ transcript: update.transcript as TranscriptTurn[] });
      }
    });

    client.on("error", (err: any) => {
      const msg = err instanceof Error ? err.message : String(err);
      set({ error: msg, isCallActive: false, agentMode: "idle" });
      _retellClient?.stopCall();
      _retellClient = null;
    });

    // ── 3. Start — must happen within 30 s of receiving the token ─────────
    await client.startCall({ accessToken, sampleRate: 24_000, emitRawAudioSamples: false });
  },

  stopCall: () => {
    _retellClient?.stopCall();
    _retellClient = null;
    set({ isCallActive: false, agentMode: "idle" });
  },

  setActivePanel:  (panel) => set({ activePanel: panel }),
  clearError:      ()      => set({ error: null }),
  clearTranscript: ()      => set({ transcript: [] }),

  reset: () => {
    _retellClient?.stopCall();
    _retellClient = null;
    set({ isCallActive: false, agentMode: "idle", transcript: [], error: null, activePanel: "pdf" });
  },
}));
