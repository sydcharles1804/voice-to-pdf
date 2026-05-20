// ─── Field schema ─────────────────────────────────────────────────────────────

export type FieldType =
  | "text"
  | "checkbox"
  | "radiobutton"
  | "dropdown"
  | "signature";

export interface FieldCoords {
  x: number;      // left edge in PDF points (72 pt = 1 inch)
  y: number;      // top edge in PDF points
  width: number;
  height: number;
}

/**
 * Canonical representation of one AcroForm field.
 * Built once at PDF upload time and stored in pdfs.fields JSONB.
 * Consumed by the AI agent to know what questions to ask, and by the
 * mobile/web app to render the voice-fill UI.
 */
export interface FieldSchema {
  id: string;           // stable UUID assigned at upload time
  name: string;         // AcroForm internal key (/T) — used when writing answers
  label: string;        // human-readable label (tooltip → nearby text → field name)
  type: FieldType;
  required: boolean;
  options: string[];    // non-empty for dropdown fields only
  pageNumber: number;   // 1-indexed page number
  coords: FieldCoords;
}

// ─── PDF document ─────────────────────────────────────────────────────────────

export type PDFRenderStatus = "pending" | "rendering" | "done" | "failed";

export interface PDFDocument {
  id: string;
  userId: string;
  name: string;
  originalName: string;
  storagePath: string;
  fileSize: number;
  pageCount: number;
  fieldCount: number;
  fields: FieldSchema[];
  createdAt: string;  // ISO 8601
  updatedAt: string;
}

export interface PDFUploadResponse {
  pdf_id: string;
  field_count: number;
  fields: FieldSchema[];
}

// ─── Session ──────────────────────────────────────────────────────────────────

export type SessionStatus = "active" | "completed" | "abandoned";

export interface Session {
  id: string;
  userId: string;
  pdfId: string;
  status: SessionStatus;
  pdfStatus?: PDFRenderStatus;
  outputPath?: string;
  /** 24-hour signed download URL. Present only when pdfStatus === "done".
   *  Regenerated on every GET /sessions/:id request — never cache this value. */
  downloadUrl?: string;
  fieldsTotal?: number;
  fieldsAnswered: number;
  skippedFields: string[];   // field names the user explicitly skipped
  retellCallId?: string;     // set when a voice call is started via POST /sessions/:id/start-call
  startedAt: string;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface FieldAnswer {
  id: string;
  sessionId: string;
  userId: string;
  fieldName: string;        // matches FieldSchema.name
  fieldLabel?: string;      // denormalised copy of FieldSchema.label at answer time
  answer?: string;
  rawTranscript?: string;
  confidence?: number;      // 0–1
  answeredAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface SessionDetail {
  session: Session;
  answers: FieldAnswer[];
}

export interface StartCallResponse {
  /** Pass to RetellWebClient.startCall() — valid for 30 seconds only, do not store. */
  access_token: string;
  /** Persist client-side; also stored in sessions.retell_call_id for webhook correlation. */
  call_id: string;
}

export interface SkipFieldRequest {
  fieldName: string;   // must match a FieldSchema.name in the session's PDF
}

export interface ChatRequest {
  message: string;     // the user's current transcribed message
}

export interface ChatResponse {
  reply: string;       // AI assistant's text reply
}

export interface ExtractRequest {
  fieldName: string;   // must match a FieldSchema.name in the session's PDF
  transcript: string;  // raw speech-to-text from the user
}

/**
 * Returned by POST /sessions/:id/extract.
 * When needsClarification is false and confidence is acceptable, pass `value`
 * directly to POST /sessions/:id/answer.
 * When needsClarification is true, surface clarificationHint to the user
 * (via the AI agent or TTS) before saving anything.
 */
export interface MapResult {
  value: string | null;            // normalized, ready-to-save value
  confidence: number;              // 0–1
  needsClarification: boolean;
  clarificationHint: string | null; // friendly follow-up question when needsClarification
}

// ─── Recording / transcription (kept for audio pipeline) ─────────────────────

export type RecordingStatus = "idle" | "recording" | "paused" | "stopped";

export interface AudioRecording {
  id: string;
  userId: string;
  filename: string;
  duration: number;   // seconds
  fileSize: number;
  mimeType: string;
  status: RecordingStatus;
  createdAt: string;
  updatedAt: string;
}

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
  confidence: number;   // 0–1
  status: TranscriptionStatus;
  wordCount: number;
  createdAt: string;
  updatedAt: string;
}

// ─── User ─────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  fullName?: string;
  avatarUrl?: string;
  createdAt: string;
  updatedAt: string;
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
