import type { AudioRecording } from "@voice-to-pdf/types";

// Placeholder — replace with real data fetching
const mockRecording: Pick<AudioRecording, "id" | "filename" | "status"> = {
  id: "demo",
  filename: "my-recording.webm",
  status: "idle",
};

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      <div className="container mx-auto px-4 py-16 max-w-2xl">
        <h1 className="text-4xl font-bold text-center text-gray-900 mb-4">
          Voice to PDF
        </h1>
        <p className="text-center text-gray-500 mb-12">
          Record your voice and instantly convert it to a formatted PDF.
        </p>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 flex flex-col items-center gap-6">
          <div className="w-24 h-24 rounded-full bg-blue-100 flex items-center justify-center">
            <svg
              className="w-10 h-10 text-blue-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
          </div>

          <button className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl transition-colors">
            Start Recording
          </button>

          <p className="text-sm text-gray-400">
            Status: <span className="font-medium">{mockRecording.status}</span>
          </p>
        </div>
      </div>
    </main>
  );
}
