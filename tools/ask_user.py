#!/usr/bin/env python3
"""
Ask-User Tool — Mandatory Turn-End User Checkpoint

Distinct from `clarify`:
  - `clarify` is LLM-initiated when stuck on ambiguity.
  - `ask_user` is a POLICY checkpoint: under the `paul-loop` personality
    every turn MUST end with a call to this tool so the user is kept in
    the loop. Free-form single-message prompt, no choice list.

Callback contract matches `clarify_tool`: the same (question, choices)
UI callback is reused so no gateway changes are required.

Handler returns JSON:
  {"response": "<user text>", "message": "<original prompt>"}
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def ask_user_tool(
    message: str,
    callback: Optional[Callable[[str, Optional[list]], str]] = None,
) -> str:
    """
    Prompt the user and return their free-form response as JSON.

    Args:
        message: free-form question / confirmation prompt.
        callback: (question, choices) -> response; choices is None here.

    Returns:
        JSON string {"response": "...", "message": "..."}.
    """
    msg = (message or "").strip()
    if not msg:
        return json.dumps({
            "error": "ask_user requires a non-empty 'message'.",
        }, ensure_ascii=False)

    if callback is None:
        # No UI wired up — degrade gracefully.
        logger.warning("ask_user invoked without a callback; returning stub.")
        return json.dumps({
            "response": "",
            "message": msg,
            "note": "No user callback available; response unset.",
        }, ensure_ascii=False)

    try:
        # Reuse clarify callback signature: (question, choices). choices=None
        # signals free-form input to the UI layer.
        response = callback(msg, None)
    except Exception as exc:
        logger.warning("ask_user callback raised: %s", exc)
        return json.dumps({
            "response": "",
            "message": msg,
            "error": f"callback failed: {exc}",
        }, ensure_ascii=False)

    response_text = "" if response is None else str(response)
    return json.dumps({
        "response": response_text,
        "message": msg,
    }, ensure_ascii=False)


def check_ask_user_requirements() -> bool:
    """Always available; runtime callback presence is checked at call time."""
    return True


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

ASK_USER_SCHEMA = {
    "name": "ask_user",
    "description": (
        "Ask the user a free-form question or request confirmation, and "
        "return their answer.\n\n"
        "Under the `paul-loop` personality every turn MUST end with a call "
        "to this tool — the model never unilaterally declares a task done; "
        "the user does. Use this to surface results, propose next steps, "
        "or confirm before moving on.\n\n"
        "Distinct from `clarify`: `clarify` is for ambiguity mid-task with "
        "optional multiple-choice; `ask_user` is for turn-end checkpoints "
        "and is always free-form."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": (
                    "Free-form message/question to surface to the user. "
                    "Summarize what was just done and ask what to do next."
                ),
            },
        },
        "required": ["message"],
    },
}


# --- Registry ---
from tools.registry import registry  # noqa: E402

registry.register(
    name="ask_user",
    toolset="ask_user",
    schema=ASK_USER_SCHEMA,
    handler=lambda args, **kw: ask_user_tool(
        message=args.get("message", ""),
        callback=kw.get("callback"),
    ),
    check_fn=check_ask_user_requirements,
    emoji="🙋",
)
