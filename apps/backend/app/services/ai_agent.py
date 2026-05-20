"""AI provider abstraction — one chat turn, one text reply.

Supports Claude (default) and OpenAI.  Provider, model, and keys are read
from environment variables so the implementation is swappable without code
changes:

    AI_PROVIDER       = claude | openai          (default: claude)
    ANTHROPIC_API_KEY = your_anthropic_api_key_here
    OPENAI_API_KEY    = your_openai_api_key_here
    AI_MODEL          = <model-id>              (optional; sensible default per provider)
    AI_MAX_TOKENS     = 512                     (optional; default 512)

The messages list follows the OpenAI / Anthropic shared format:
    [{"role": "user"|"assistant", "content": "..."}]

The system prompt is always passed separately so the caller (chat route) can
rebuild it per-turn with the latest answered-fields state.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_PROVIDER   = os.getenv("AI_PROVIDER", "claude").lower()
_ANTH_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
_OAI_KEY    = os.getenv("OPENAI_API_KEY", "")
_MODEL_OVERRIDE = os.getenv("AI_MODEL", "")
_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "512"))

# Sensible defaults — Haiku for Claude (fast, cheap for Q&A loops),
# gpt-4o-mini for OpenAI (similar cost profile).
_DEFAULT_MODEL: dict[str, str] = {
    "claude": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}


def _active_model() -> str:
    return _MODEL_OVERRIDE or _DEFAULT_MODEL.get(_PROVIDER, "claude-haiku-4-5-20251001")


def chat(system_prompt: str, messages: list[dict]) -> str:
    """Send one conversational turn and return the assistant's text reply.

    Args:
        system_prompt: Fully-rendered prompt from ``prompt_builder``.
        messages:      Full conversation history, oldest first.
                       The last item must have ``role == "user"``.

    Returns:
        The assistant's reply as a plain string.

    Raises:
        RuntimeError: Missing API key, missing package, or provider error.
    """
    if _PROVIDER == "openai":
        return _openai_chat(system_prompt, messages)
    return _claude_chat(system_prompt, messages)


# ── Claude ────────────────────────────────────────────────────────────────────

def _claude_chat(system_prompt: str, messages: list[dict]) -> str:
    if not _ANTH_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to apps/backend/.env or set AI_PROVIDER=openai."
        )
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package is not installed — run: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=_ANTH_KEY)
    model  = _active_model()

    logger.debug("claude chat | model=%s messages=%d", model, len(messages))

    response = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _openai_chat(system_prompt: str, messages: list[dict]) -> str:
    if not _OAI_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Add it to apps/backend/.env or set AI_PROVIDER=claude."
        )
    try:
        import openai
    except ImportError:
        raise RuntimeError(
            "openai package is not installed — run: pip install openai"
        )

    client = openai.OpenAI(api_key=_OAI_KEY)
    model  = _active_model()

    # OpenAI puts the system prompt as the first message.
    all_messages = [{"role": "system", "content": system_prompt}] + messages

    logger.debug("openai chat | model=%s messages=%d", model, len(all_messages))

    response = client.chat.completions.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        messages=all_messages,
    )
    return response.choices[0].message.content
