"use client";

import { type AgentMode, type TranscriptTurn } from "@/hooks/useRetellCall";

interface VoiceCallButtonProps {
  sessionId:    string;
  isCallActive: boolean;
  agentMode:    AgentMode;
  transcript:   TranscriptTurn[];
  error:        string | null;
  onStart:      () => void;
  onStop:       () => void;
}

const MODE_LABEL: Record<AgentMode, string> = {
  idle:      "Start Voice Call",
  listening: "Listening…",
  speaking:  "Agent speaking…",
};

const MODE_COLOR: Record<AgentMode, string> = {
  idle:      "bg-blue-600 hover:bg-blue-700",
  listening: "bg-green-600 hover:bg-green-700",
  speaking:  "bg-amber-500 hover:bg-amber-600",
};

export function VoiceCallButton({
  isCallActive,
  agentMode,
  transcript,
  error,
  onStart,
  onStop,
}: VoiceCallButtonProps) {
  return (
    <div className="flex flex-col items-center gap-4 w-full">
      {error && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2 w-full text-center">
          {error}
        </p>
      )}

      <button
        onClick={isCallActive ? onStop : onStart}
        className={`px-8 py-3 text-white font-semibold rounded-xl transition-colors ${
          isCallActive ? "bg-red-600 hover:bg-red-700" : MODE_COLOR[agentMode]
        }`}
      >
        {isCallActive ? "End Call" : MODE_LABEL[agentMode]}
      </button>

      {transcript.length > 0 && (
        <div className="w-full rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-2 max-h-52 overflow-y-auto">
          {transcript.map((turn, i) => (
            <div
              key={i}
              className={`text-sm ${
                turn.role === "agent" ? "text-blue-700" : "text-gray-800"
              }`}
            >
              <span className="font-medium capitalize">{turn.role}: </span>
              {turn.content}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
