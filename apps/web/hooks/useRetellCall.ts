"use client";

import { useCallback, useRef, useState } from "react";
import { RetellWebClient } from "retell-client-js-sdk";

export type AgentMode = "idle" | "listening" | "speaking";

export interface TranscriptTurn {
  role: "agent" | "user";
  content: string;
}

interface UseRetellCallOptions {
  /** Base URL of your FastAPI backend, e.g. "http://localhost:8000" */
  apiBase: string;
  /** Supabase JWT to authenticate the start-call request */
  authToken: string;
}

export function useRetellCall({ apiBase, authToken }: UseRetellCallOptions) {
  const clientRef  = useRef<RetellWebClient | null>(null);

  const [isCallActive, setIsCallActive] = useState(false);
  const [agentMode,    setAgentMode]    = useState<AgentMode>("idle");
  const [transcript,   setTranscript]   = useState<TranscriptTurn[]>([]);
  const [callId,       setCallId]       = useState<string | null>(null);
  const [error,        setError]        = useState<string | null>(null);

  const startCall = useCallback(async (sessionId: string) => {
    setError(null);

    // 1. Ask our backend to create the Retell web call.
    let accessToken: string;
    let newCallId: string;
    try {
      const res = await fetch(`${apiBase}/sessions/${sessionId}/start-call`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const { data } = await res.json();
      accessToken = data.access_token;
      newCallId   = data.call_id;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to start call";
      setError(msg);
      return;
    }

    // 2. Build the client and register all listeners BEFORE startCall().
    const client = new RetellWebClient();
    clientRef.current = client;

    client.on("call_started", () => {
      setIsCallActive(true);
      setAgentMode("listening");
      setCallId(newCallId);
    });

    client.on("call_ended", () => {
      setIsCallActive(false);
      setAgentMode("idle");
      clientRef.current = null;
    });

    client.on("agent_start_talking", () => setAgentMode("speaking"));
    client.on("agent_stop_talking",  () => setAgentMode("listening"));

    client.on("update", (update) => {
      // update.transcript is the last ~5 turns as an array of {role, content}
      if (Array.isArray(update.transcript)) {
        setTranscript(update.transcript as TranscriptTurn[]);
      }
    });

    client.on("error", (err) => {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      client.stopCall();
      setIsCallActive(false);
      setAgentMode("idle");
      clientRef.current = null;
    });

    // 3. Start — must happen within 30 seconds of receiving the access_token.
    await client.startCall({
      accessToken,
      sampleRate: 24000,
      emitRawAudioSamples: false,
    });
  }, [apiBase, authToken]);

  const stopCall = useCallback(() => {
    clientRef.current?.stopCall();
    clientRef.current = null;
    setIsCallActive(false);
    setAgentMode("idle");
  }, []);

  return { startCall, stopCall, isCallActive, agentMode, transcript, callId, error };
}
