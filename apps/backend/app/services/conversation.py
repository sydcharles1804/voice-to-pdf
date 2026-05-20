"""Conversation state management for voice-fill sessions.

All functions are pure or take explicit arguments — no FastAPI, no globals.
The chat route is the only caller; it owns the DB reads and writes.

Sliding-window contract
-----------------------
WINDOW_SIZE controls how many turns are kept in ``sessions.conversation_history``.
New turns are always appended to the end; old turns are dropped from the front.
The system prompt (field schema + progress + current-task section) is rebuilt
fresh on every call, so the window does NOT need to include an opening
"context-setting" message — the system prompt provides that context.

A turn is one dict: ``{"role": "user"|"assistant", "content": "..."}``
One exchange = 2 turns (user + assistant).  WINDOW_SIZE = 8 keeps 4 exchanges.
"""

from __future__ import annotations

from typing import Any, Collection

WINDOW_SIZE = 8  # max turns stored; keeps 4 full user↔assistant exchanges


# ── Cursor ────────────────────────────────────────────────────────────────────

def derive_cursor(
    fields: list[dict],
    answered_names: Collection[str],
    skipped_names: Collection[str] = (),
) -> tuple[dict[str, Any] | None, int]:
    """Return the first unanswered, non-skipped field and its 0-based index.

    Returns ``(None, len(fields))`` when every field is answered or skipped.
    The index is used by the prompt builder to say "field 3 of 7".
    """
    excluded = set(answered_names) | set(skipped_names)
    for i, field in enumerate(fields):
        if field["name"] not in excluded:
            return field, i
    return None, len(fields)


def find_field_by_hint(fields: list[dict], hint: str) -> dict[str, Any] | None:
    """Return the field whose label best matches ``hint`` (case-insensitive).

    Tries exact match first, then substring. Returns None if nothing matches.
    Used to resolve CORRECT_PREVIOUS intent when the user names a prior field.
    """
    hint_lower = hint.lower().strip()
    for field in fields:
        if (field.get("label") or field["name"]).lower() == hint_lower:
            return field
    for field in fields:
        if hint_lower in (field.get("label") or field["name"]).lower():
            return field
    return None


# ── History helpers ───────────────────────────────────────────────────────────

def load_history(session_row: dict) -> list[dict]:
    """Extract the stored turn list from a session DB row.

    Safe to call with any dict — returns [] if the column is absent or null.
    """
    raw = session_row.get("conversation_history")
    if not isinstance(raw, list):
        return []
    return raw


def append_turns(
    history: list[dict],
    new_turns: list[dict],
    window: int = WINDOW_SIZE,
) -> list[dict]:
    """Append ``new_turns`` to ``history`` and trim the front to ``window`` items.

    Args:
        history:   Current stored turns (from ``load_history``).
        new_turns: Turns to add this round, typically
                   ``[{"role": "user", ...}, {"role": "assistant", ...}]``.
        window:    Maximum number of turns to retain (default ``WINDOW_SIZE``).

    Returns:
        A new list — the caller is responsible for writing it back to the DB.
    """
    combined = history + new_turns
    if len(combined) > window:
        combined = combined[-window:]
    return combined
