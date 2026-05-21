"use client";

import { useSession } from "@/context/SessionContext";
import { useMicLevel } from "@/hooks/useMicLevel";
import { useSessionStore } from "@/store/sessionStore";

// ── Config per agent mode ─────────────────────────────────────────────────────

const RING_CLASS: Record<string, string> = {
  listening: "bg-emerald-400",
  speaking:  "bg-blue-400",
};

const RING_ANIM: Record<string, string> = {
  listening: "animate-mic-ring",
  speaking:  "animate-mic-ring-fast",
};

const RING_ANIM_DELAY: Record<string, string> = {
  listening: "animate-mic-ring-delay",
  speaking:  "animate-mic-ring-fast-delay",
};

const BUTTON_STYLE: Record<string, string> = {
  idle:      "bg-white border-2 border-gray-200 text-gray-400 hover:border-blue-300 hover:text-blue-500 hover:shadow-md",
  listening: "bg-gradient-to-br from-emerald-400 to-green-600 text-white shadow-xl shadow-emerald-500/40",
  speaking:  "bg-gradient-to-br from-blue-500 to-indigo-600   text-white shadow-xl shadow-blue-500/40",
};

const STATUS_TEXT: Record<string, string> = {
  idle:      "Tap to start",
  listening: "Listening…",
  speaking:  "Agent speaking…",
};

const STATUS_COLOR: Record<string, string> = {
  idle:      "text-gray-400",
  listening: "text-emerald-600",
  speaking:  "text-blue-600",
};

// ── Component ─────────────────────────────────────────────────────────────────

export function MicButton({ size = "lg" }: { size?: "sm" | "lg" }) {
  const { sessionId, authToken, apiBase } = useSession();
  const { isCallActive, agentMode, startCall, stopCall, error, clearError } =
    useSessionStore();

  const isListening = isCallActive && agentMode === "listening";
  const micLevel    = useMicLevel(isListening);

  const mode = isCallActive ? agentMode : "idle";

  // Mic level drives an extra scale on the outer ring (0 = 1×, 1 = 1.3×)
  const dynamicScale = isListening && micLevel > 0.05
    ? 1 + micLevel * 0.4
    : 1;

  const btnSize  = size === "sm" ? "w-14 h-14" : "w-20 h-20";
  const ringSize = size === "sm" ? "h-20 w-20"  : "h-28 w-28";
  const ring2Sz  = size === "sm" ? "h-16 w-16"  : "h-20 w-20";
  const iconSize = size === "sm" ? "w-5 h-5"    : "w-7 h-7";

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <div className="relative flex items-center justify-center">
        {/* ── Dynamic outer ring (Web Audio level-driven) ── */}
        {isListening && (
          <span
            className={`absolute ${ringSize} rounded-full ${RING_CLASS[mode]} opacity-20 transition-transform duration-75`}
            style={{ transform: `scale(${dynamicScale})` }}
          />
        )}

        {/* ── Animated CSS ripple rings ── */}
        {isCallActive && mode !== "idle" && (
          <>
            <span className={`absolute ${ringSize} rounded-full ${RING_CLASS[mode]} opacity-30 ${RING_ANIM[mode]}`} />
            <span className={`absolute ${ring2Sz} rounded-full ${RING_CLASS[mode]} opacity-40 ${RING_ANIM_DELAY[mode]}`} />
          </>
        )}

        {/* ── Main button ── */}
        <button
          onClick={() => {
            clearError();
            isCallActive ? stopCall() : startCall(sessionId, apiBase, authToken);
          }}
          aria-label={isCallActive ? "End call" : "Start voice call"}
          className={[
            `relative z-10 ${btnSize} rounded-full flex items-center justify-center`,
            "transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400",
            isCallActive ? "scale-110" : "scale-100",
            BUTTON_STYLE[mode],
          ].join(" ")}
        >
          {isCallActive ? (
            /* Stop square */
            <svg className={iconSize} viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            /* Mic icon */
            <svg className={iconSize} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
          )}
        </button>
      </div>

      {/* ── Status label ── */}
      <p className={`text-sm font-medium transition-colors ${STATUS_COLOR[mode]}`}>
        {STATUS_TEXT[mode]}
      </p>

      {/* ── Error message ── */}
      {error && (
        <p className="text-xs text-red-500 max-w-[14rem] text-center leading-relaxed">
          {error}
        </p>
      )}
    </div>
  );
}
