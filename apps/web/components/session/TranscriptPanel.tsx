"use client";

import { useEffect, useRef } from "react";
import { useSessionStore, type TranscriptTurn } from "@/store/sessionStore";

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center">
        <svg className="w-6 h-6 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-600">Conversation</p>
        <p className="text-xs text-gray-400 mt-1">Start the call to see the transcript here</p>
      </div>
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ turn, index }: { turn: TranscriptTurn; index: number }) {
  const isAgent = turn.role === "agent";

  return (
    <div
      className={`flex gap-2 animate-msg-in ${isAgent ? "flex-row" : "flex-row-reverse"}`}
      style={{ animationDelay: `${Math.min(index * 20, 100)}ms` }}
    >
      {/* Avatar */}
      <div
        className={[
          "shrink-0 w-7 h-7 rounded-full flex items-center justify-center",
          "text-xs font-bold mt-0.5",
          isAgent ? "bg-blue-100 text-blue-600" : "bg-gray-100 text-gray-500",
        ].join(" ")}
      >
        {isAgent ? "A" : "Y"}
      </div>

      {/* Bubble */}
      <div
        className={[
          "max-w-[78%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
          isAgent
            ? "bg-blue-50   text-blue-900  rounded-tl-sm"
            : "bg-gray-100  text-gray-800  rounded-tr-sm",
        ].join(" ")}
      >
        {turn.content}
      </div>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

export function TranscriptPanel() {
  const transcript  = useSessionStore(s => s.transcript);
  const isActive    = useSessionStore(s => s.isCallActive);
  const agentMode   = useSessionStore(s => s.agentMode);
  const scrollRef   = useRef<HTMLDivElement>(null);
  const prevLenRef  = useRef(0);

  // Scroll to bottom when new message arrives.
  useEffect(() => {
    if (transcript.length !== prevLenRef.current) {
      prevLenRef.current = transcript.length;
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }
  }, [transcript]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          Conversation
        </span>
        {isActive && (
          <span className={[
            "inline-flex items-center gap-1.5 text-xs font-medium",
            agentMode === "speaking"  ? "text-blue-500"    :
            agentMode === "listening" ? "text-emerald-500" :
            "text-gray-400",
          ].join(" ")}>
            <span className={[
              "w-1.5 h-1.5 rounded-full",
              agentMode === "speaking"  ? "bg-blue-500 animate-pulse"    :
              agentMode === "listening" ? "bg-emerald-500 animate-pulse" :
              "bg-gray-300",
            ].join(" ")} />
            {agentMode === "speaking" ? "Speaking" : "Listening"}
          </span>
        )}
      </div>

      {/* Message list */}
      {transcript.length === 0 ? (
        <EmptyState />
      ) : (
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto flex flex-col gap-3 p-4 scroll-smooth"
        >
          {transcript.map((turn, i) => (
            <MessageBubble key={i} turn={turn} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
