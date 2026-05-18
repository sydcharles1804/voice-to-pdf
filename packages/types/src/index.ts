// ─── Recording ────────────────────────────────────────────────────────────────

export type RecordingStatus = "idle" | "recording" | "paused" | "stopped";

export interface AudioRecording {
  id: string;
  userId: string;
  filename: string;
  /** Duration in seconds */
  duration: number;
  /** File size in bytes */
  fileSize: number;
  mimeType: string;
  status: RecordingStatus;
  createdAt: string; // ISO 8601
  updatedAt: string;
}

// ─── Transcription ────────────────────────────────────────────────────────────

export type TranscriptionStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

export interface TranscriptionResult {
  id: string;
  recordingId: string;
  text: string;
  language: string;
  /** Confidence score 0–1 */
  confidence: number;
  status: TranscriptionStatus;
  wordCount: number;
  createdAt: string;
  updatedAt: string;
}

// ─── PDF ──────────────────────────────────────────────────────────────────────

export type PDFStatus = "pending" | "generating" | "completed" | "failed";

export interface PDFDocument {
  id: string;
  transcriptionId: string;
  userId: string;
  filename: string;
  fileSize: number;
  pageCount: number;
  status: PDFStatus;
  downloadUrl?: string;
  createdAt: string;
  updatedAt: string;
}

// ─── User ─────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: string;
}

// ─── API helpers ──────────────────────────────────────────────────────────────

export interface ApiResponse<T> {
  data: T;
  message: string;
  success: boolean;
}

export interface ApiError {
  message: string;
  code: string;
  statusCode: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNextPage: boolean;
}
