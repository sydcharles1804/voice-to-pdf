"use client";

import { useSessionStore } from "@/store/sessionStore";

const TABS = [
  {
    key:  "pdf",
    label: "Form",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    ),
  },
  {
    key:  "transcript",
    label: "Chat",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        />
      </svg>
    ),
  },
] as const;

export function ViewToggle() {
  const { activePanel, setActivePanel } = useSessionStore();

  return (
    <div className="flex bg-gray-100 rounded-xl p-1 gap-1">
      {TABS.map(tab => (
        <button
          key={tab.key}
          onClick={() => setActivePanel(tab.key)}
          className={[
            "flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-all",
            activePanel === tab.key
              ? "bg-white text-gray-900 shadow-sm"
              : "text-gray-500 hover:text-gray-700",
          ].join(" ")}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
