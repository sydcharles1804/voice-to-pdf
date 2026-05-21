"use client";

import dynamic from "next/dynamic";
import { useSession } from "@/context/SessionContext";
import { useSessionStore } from "@/store/sessionStore";
import { MicButton } from "./MicButton";
import { TranscriptPanel } from "./TranscriptPanel";
import { ViewToggle } from "./ViewToggle";

// PDF viewer is client-only (pdfjs uses canvas).
const PDFViewer = dynamic(
  () => import("@/components/PDFViewer").then(m => m.PDFViewer),
  {
    ssr:     false,
    loading: () => (
      <div className="w-full h-full bg-gray-100 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    ),
  },
);

// ── "Now asking" chip shown above the mic ─────────────────────────────────────

function CurrentFieldChip() {
  const { fields, currentFieldName } = useSession();
  const isCallActive = useSessionStore(s => s.isCallActive);

  if (!isCallActive || !currentFieldName) return null;
  const field = fields.find(f => f.name === currentFieldName);
  if (!field) return null;

  return (
    <div className="w-full max-w-xs rounded-xl bg-blue-50 border border-blue-100 px-4 py-2.5 text-center">
      <p className="text-[10px] font-semibold text-blue-400 uppercase tracking-widest mb-0.5">
        Now asking
      </p>
      <p className="text-sm font-semibold text-blue-700 truncate">
        {field.label || field.name}
      </p>
    </div>
  );
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function ProgressBar() {
  const { answeredNames, fieldCount } = useSession();
  const pct = fieldCount > 0 ? (answeredNames.size / fieldCount) * 100 : 0;

  return (
    <div className="flex items-center gap-2 flex-1 min-w-0">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 shrink-0 tabular-nums">
        {answeredNames.size}/{fieldCount}
      </span>
    </div>
  );
}

// ── Mic dock — shared between desktop sidebar and mobile bottom bar ───────────

function MicDock() {
  return (
    <div className="shrink-0 flex flex-col items-center gap-4 px-6 py-6 bg-white border-t border-gray-100">
      <CurrentFieldChip />
      <MicButton />
    </div>
  );
}

// ── PDF panel ─────────────────────────────────────────────────────────────────

function PDFPanel() {
  const { templateUrl, fields, answeredNames, skippedNames, currentFieldName } = useSession();

  if (!templateUrl) {
    return (
      <div className="w-full h-full bg-gray-100 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <PDFViewer
      pdfUrl={templateUrl}
      fields={fields}
      answeredNames={answeredNames}
      skippedNames={skippedNames}
      currentFieldName={currentFieldName}
    />
  );
}

// ── Main session view ─────────────────────────────────────────────────────────

interface SessionViewProps {
  onBack: () => void;
}

export function SessionView({ onBack }: SessionViewProps) {
  const { pdfName } = useSession();
  const activePanel = useSessionStore(s => s.activePanel);

  return (
    <div className="flex flex-col h-screen bg-gray-50 overflow-hidden">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="shrink-0 bg-white border-b border-gray-100 px-4 py-3 flex items-center gap-3">
        <button
          onClick={onBack}
          aria-label="Back to library"
          className="shrink-0 text-gray-400 hover:text-gray-600 transition-colors p-1 -ml-1 rounded-lg hover:bg-gray-100"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <div className="flex-1 min-w-0 flex items-center gap-3">
          <p className="text-sm font-bold text-gray-900 truncate shrink-0 max-w-[120px] sm:max-w-none">
            {pdfName}
          </p>
          <ProgressBar />
        </div>

        {/* Mobile toggle — hidden on desktop */}
        <div className="lg:hidden shrink-0">
          <ViewToggle />
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 flex flex-col lg:flex-row">

        {/* PDF panel
            Desktop: always visible (flex-1)
            Mobile:  only visible when activePanel === 'pdf' */}
        <div
          className={[
            "lg:flex-1 lg:flex flex-col border-r border-gray-200",
            activePanel === "pdf" ? "flex flex-1" : "hidden",
          ].join(" ")}
        >
          <PDFPanel />
        </div>

        {/* Right sidebar: transcript + mic dock
            Desktop: fixed 320px wide, always visible
            Mobile:  only visible when activePanel === 'transcript' */}
        <div
          className={[
            "lg:w-80 xl:w-96 lg:flex flex-col bg-white",
            activePanel === "transcript" ? "flex flex-1" : "hidden",
          ].join(" ")}
        >
          <div className="flex-1 min-h-0 overflow-hidden">
            <TranscriptPanel />
          </div>
          <MicDock />
        </div>
      </div>

      {/* ── Mobile-only bottom mic bar (only when PDF panel is active) ─────── */}
      <div
        className={[
          "lg:hidden shrink-0",
          activePanel === "pdf" ? "block" : "hidden",
        ].join(" ")}
      >
        <MicDock />
      </div>
    </div>
  );
}
