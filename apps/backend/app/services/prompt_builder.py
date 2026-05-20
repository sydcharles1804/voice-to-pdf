"""Dynamically build the LLM system prompt from a session's field schema.

Rebuilt on every chat turn so the prompt always reflects the current set of
answered / unanswered fields.  Callers pass the full ``fields`` list from
``pdfs.fields`` plus the set of field names already recorded for the session.
"""

from __future__ import annotations

from typing import Collection

# ── Base type hints (keyed by FieldSchema.type) ───────────────────────────────
# Shown verbatim when the field type alone is enough.
_BASE_HINTS: dict[str, str] = {
    "checkbox": (
        'Yes/No field. Accept any affirmative ("yes", "y", "correct", "true") '
        'as yes; anything negative as no.'
    ),
    "radiobutton": (
        "Single-choice field. The answer must be exactly one of the listed options. "
        "Read the options aloud and ask the user to pick one."
    ),
    "dropdown": (
        "Single-choice field. The answer must be exactly one of the listed options. "
        "Read the options aloud and ask the user to pick one."
    ),
    "signature": (
        "Legal signature. Ask the user to state their full legal name clearly. "
        "Spell it back letter-by-letter if needed to confirm."
    ),
}

# ── Label-pattern sub-type hints for plain "text" fields ─────────────────────
# Checked against the lower-cased field label; first match wins.
_LABEL_HINTS: list[tuple[str, str]] = [
    ("date of birth", "Date of birth — ask in MM/DD/YYYY format. If the user says 'January 5th 1990', convert to 01/05/1990 and confirm the exact date before recording."),
    ("dob",           "Date of birth — ask in MM/DD/YYYY format. If the user says a natural date, convert it to MM/DD/YYYY and confirm."),
    ("birth",         "Date of birth — ask in MM/DD/YYYY format. Convert natural language dates and confirm."),
    ("date",          "Date field — tell the user you need MM/DD/YYYY before they answer. If they say 'last Tuesday' or 'January 5th', convert to MM/DD/YYYY and confirm."),
    ("phone",         "Phone number — guide the user to (XXX) XXX-XXXX or XXX-XXX-XXXX format."),
    ("mobile",        "Mobile number — guide the user to (XXX) XXX-XXXX or XXX-XXX-XXXX format."),
    ("fax",           "Fax number — guide the user to (XXX) XXX-XXXX format."),
    ("email",         "Email address — guide the user to name@domain.com. If unclear, ask them to spell the domain."),
    ("zip",           "ZIP or postal code — expect 5 digits (US) or the local postal format."),
    ("postal",        "ZIP or postal code — expect 5 digits (US) or the local postal format."),
    ("ssn",           "Social Security Number — expect XXX-XX-XXXX. Tell the user this is sensitive and will be kept secure before asking."),
    ("ein",           "Employer Identification Number — expect XX-XXXXXXX."),
    ("tax id",        "Tax ID number — expect XX-XXXXXXX for an EIN, or XXX-XX-XXXX for an SSN."),
    ("salary",        "Salary or compensation — accept a plain number or dollar figure (e.g. 50000 or $50,000)."),
    ("income",        "Income amount — accept a plain number or dollar figure."),
    ("amount",        "Dollar amount — accept a plain number or dollar figure (e.g. 1500 or $1,500)."),
    ("percent",       "Percentage — accept a number between 0 and 100, with or without the % sign."),
    ("rate",          "Rate or percentage — accept a number, with or without the % sign."),
    ("url",           "Website URL — guide the user to include https:// if they omit it."),
    ("website",       "Website URL — guide the user to include https:// if they omit it."),
]


def _format_hint(field: dict) -> str | None:
    """Return the type or format guidance line for one field, or None."""
    ftype = field.get("type", "text")

    if ftype == "text":
        label_lower = (field.get("label") or "").lower()
        for keyword, hint in _LABEL_HINTS:
            if keyword in label_lower:
                return hint
        return None  # plain text — no special guidance needed

    base = _BASE_HINTS.get(ftype)
    if not base:
        return None

    # Append the option list for choice fields.
    if ftype in ("dropdown", "radiobutton"):
        opts = field.get("options") or []
        if opts:
            quoted = ", ".join(f'"{o}"' for o in opts)
            return f"{base} Valid options: {quoted}."

    return base


def build_system_prompt(
    fields: list[dict],
    answered_names: Collection[str] = (),
    skipped_names: Collection[str] = (),
    current_field: dict | None = None,
    current_field_index: int | None = None,
) -> str:
    """Return the fully-rendered system prompt for the form-filling AI agent.

    Args:
        fields:               Full ``FieldSchema`` list from ``pdfs.fields``.
        answered_names:       Field names already confirmed for this session.
        skipped_names:        Optional field names the user explicitly skipped.
        current_field:        The next field the LLM should ask about.
        current_field_index:  0-based position of ``current_field`` in ``fields``.

    The prompt is intentionally concise — every line the LLM reads is a token
    it must process on every call.  Rules are numbered so the model can cite
    them if it needs to reason about edge cases.
    """
    answered_set = set(answered_names)
    skipped_set  = set(skipped_names)
    excluded_set = answered_set | skipped_set
    unanswered   = [f for f in fields if f["name"] not in excluded_set]
    n_total      = len(fields)
    n_done       = len(answered_set)

    # ── Field list ────────────────────────────────────────────────────────────
    field_blocks: list[str] = []
    for idx, field in enumerate(fields, 1):
        name     = field["name"]
        label    = field.get("label") or name
        ftype    = field.get("type", "text")
        required = field.get("required", False)
        page     = field.get("pageNumber", 1)
        is_done    = name in answered_set
        is_skipped = name in skipped_set

        if is_done:
            tag = "DONE — skip"
        elif is_skipped:
            tag = "SKIPPED — user opted out"
        elif required:
            tag = "REQUIRED"
        else:
            tag = "optional"

        hint = _format_hint(field)

        lines = [f"{idx}. **{label}** [{tag}]"]
        lines.append(f"   ID: `{name}` | page {page} | type: {ftype}")
        if hint:
            lines.append(f"   Format: {hint}")

        field_blocks.append("\n".join(lines))

    fields_section = "\n\n".join(field_blocks)

    # ── Progress line ─────────────────────────────────────────────────────────
    if n_done == 0 and not skipped_set:
        progress = "No fields answered yet. Begin with field 1."
    elif not unanswered:
        progress = (
            f"{n_done}/{n_total} fields answered"
            + (f", {len(skipped_set)} skipped" if skipped_set else "")
            + ". Proceed to the summary and confirmation step."
        )
    else:
        remaining = [f.get("label") or f["name"] for f in unanswered]
        progress = (
            f"{n_done}/{n_total} fields answered"
            + (f", {len(skipped_set)} skipped" if skipped_set else "")
            + f". Still needed: {', '.join(remaining)}."
        )

    # ── Current-task section ──────────────────────────────────────────────────
    if current_field is not None:
        cf_label = current_field.get("label") or current_field["name"]
        cf_hint  = _format_hint(current_field)
        cf_pos   = (
            f"field {current_field_index + 1} of {n_total}"
            if current_field_index is not None
            else f"of {n_total}"
        )
        task_lines = [
            f"Ask about this field next: **{cf_label}** ({cf_pos}).",
            "Do not ask about any other field until this one is answered and confirmed.",
        ]
        if cf_hint:
            task_lines.append(f"Format guidance: {cf_hint}")
        current_task_section = "\n".join(task_lines)
    else:
        current_task_section = (
            "All fields are answered. "
            "Read back every field and its recorded value, "
            "then ask the user to confirm before finishing."
        )

    # ── Final prompt ──────────────────────────────────────────────────────────
    return f"""\
You are a voice-powered form-filling assistant. Your only job is to collect \
answers for the fields listed below by having a natural, patient conversation.

## Intent detection

Before responding, silently classify the user's message into exactly one intent:

- **ANSWER** — the user is providing or attempting to provide an answer to the \
current field (this is the default when the message doesn't clearly match the others).
- **SKIP** — the user wants to skip the current field. \
Trigger phrases: "skip", "skip that", "move on", "next question", "leave it blank", \
"I don't know", "pass".
- **REPEAT_QUESTION** — the user wants the question repeated or doesn't understand. \
Trigger phrases: "what?", "repeat that", "say that again", "can you repeat", \
"what did you ask", "huh", "I don't understand".
- **CORRECT_PREVIOUS** — the user wants to change an answer already given. \
Trigger phrases: "actually", "wait", "I made a mistake", "that's wrong", \
"change my", "go back", "I meant", "let me fix".

Respond based on the detected intent:

**If ANSWER:** Extract the value, confirm it ("Got it — I'll record [value] for \
[label]."), then ask the next unanswered field.

**If SKIP and field is optional:** Say "OK, I'll skip [label] for now." and \
immediately ask the next unanswered field. Do not record any value for the skipped field.

**If SKIP and field is REQUIRED:** Say "[Label] is required and can't be skipped." \
Then re-ask the question. Do not advance.

**If REPEAT_QUESTION:** Re-read the current question with its full format guidance. \
Do not advance to the next field.

**If CORRECT_PREVIOUS:** Identify which field the user wants to correct — they may \
name it directly ("my phone number") or vaguely ("the last one"). If ambiguous, ask \
"Which field would you like to correct?" and list the answered fields. Once the \
field is identified, re-ask its question as if it were new. When the user gives the \
new answer, confirm: "Got it — I'll update [label] to [new value]."

## Rules

1. **One question at a time.** Never ask about more than one field per reply.
2. **Announce the format first.** If a field has a required format (date, phone, \
email, etc.), state the expected format *before* the user answers. \
Example: "What is your date of birth? Please say it as month/day/year."
3. **Confirm each answer.** After the user responds, say: \
"Got it — I'll record [exact value] for [label]." \
Then immediately ask about the next unanswered field.
4. **Clarify when needed.** If an answer is vague, ambiguous, or in the wrong \
format, ask one focused follow-up before moving on. Do not advance until you \
have a clean, usable answer.
5. **Use labels only.** Never say internal field IDs (like `field_142`) to the \
user — they are for your reference only.
6. **Skip answered fields.** Fields marked DONE are already recorded; \
do not ask about them again unless the user explicitly asks to correct one.
7. **Required fields must be filled.** Fields marked REQUIRED cannot be skipped \
or left blank.
8. **End with a summary.** Once all fields are answered (or skipped where allowed), \
read back every answered field and its value, then ask the user to confirm.

## Form fields ({n_total} total)

{fields_section}

## Progress

{progress}

## Current task

{current_task_section}"""
