-- Migration: add_call_transcript_to_sessions
-- Run this in the Supabase dashboard → SQL Editor

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS call_transcript      JSONB,
  ADD COLUMN IF NOT EXISTS call_transcript_text TEXT,
  ADD COLUMN IF NOT EXISTS call_analysis        JSONB;

COMMENT ON COLUMN sessions.call_transcript IS
  'Structured Retell transcript from call_ended webhook. '
  'Array of {role, content, words[]} objects with timestamps. '
  'Used by the review screen and as the audit trail.';

COMMENT ON COLUMN sessions.call_transcript_text IS
  'Plain-text version of the Retell transcript. Used for display and search.';

COMMENT ON COLUMN sessions.call_analysis IS
  'Post-call analysis from Retell call_analyzed webhook. '
  'Contains sentiment, summary, and any custom analysis data.';
