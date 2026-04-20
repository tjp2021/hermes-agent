#!/usr/bin/env python3
"""
Task-state file I/O for paul-loop personality.

Durable scratchpad at <cwd>/.hermes/task-state.md that the agent reads at
the start of every turn and writes at the end, so critical state (todo
list, current unit, rubber-duck round, last ask_user answer) survives
context compaction.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


TASK_STATE_DIR = ".hermes"
TASK_STATE_FILE = "task-state.md"

# Sentinel text used to detect the paul-loop personality without plumbing a
# personality name through every subsystem. The personality's system_prompt
# (configured in cli.py agent.personalities["paul-loop"]) starts with this
# header, so we can opt-in purely based on whether the string is present in
# the current system prompt. This keeps the feature fully backwards-compatible.
PAUL_LOOP_SENTINEL = "PAUL-LOOP MODE (strict user-in-the-loop operator mode):"


# Verbatim rule block re-injected after context compression (Primitive 5) and
# used by prompt-builder injection (Primitive 4 injection stub). Kept in sync
# with the personality string in cli.py.
PAUL_LOOP_RULES = (
    "PAUL-LOOP MODE (strict user-in-the-loop operator mode):\n"
    "\n"
    "Operating rules — NEVER violate these, even after context compaction:\n"
    "\n"
    "1. DELEGATE EVERYTHING. All non-trivial work (research, writing, analysis, "
    "coding) goes through delegate_task subagents. You are an orchestrator, not a doer.\n"
    "\n"
    "2. RUBBER-DUCK EVERY UNIT. After every unit of work (a plan, a draft, a code "
    "change), call rubber_duck with the artifact. Apply the agreed critiques. "
    "Re-call rubber_duck. Continue until status='converged' or max_rounds_exceeded.\n"
    "\n"
    "3. END EVERY TURN WITH ask_user. You never declare completion. After rubber-duck "
    "converges on a unit, call ask_user to surface the result and ask whether to "
    "proceed. The user decides when the session ends.\n"
    "\n"
    "4. REHYDRATE FROM STATE. At the start of every turn, read .hermes/task-state.md "
    "in the working directory if it exists. It contains your todo list, the current "
    "unit under work, the rubber-duck round, and the last ask_user answer. Update it "
    "at the end of every turn before calling ask_user.\n"
    "\n"
    "5. NEVER TRUST POST-COMPACTION MEMORY. If this system prompt is your first "
    "injection after a compaction event, assume the prior conversation is lossy. "
    "Re-read .hermes/task-state.md as ground truth before acting.\n"
)


def is_paul_loop_active(system_prompt: str | None) -> bool:
    """Return True when the active system prompt includes the paul-loop sentinel."""
    if not system_prompt:
        return False
    return PAUL_LOOP_SENTINEL in system_prompt


def _state_path(cwd: str) -> Path:
    return Path(cwd) / TASK_STATE_DIR / TASK_STATE_FILE


def read_task_state(cwd: str) -> str:
    """
    Return the contents of <cwd>/.hermes/task-state.md, or "" if missing
    or unreadable. Never raises.
    """
    if not cwd:
        return ""
    try:
        path = _state_path(cwd)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def write_task_state(cwd: str, content: str) -> None:
    """
    Atomically write `content` to <cwd>/.hermes/task-state.md.

    Creates the .hermes directory if it doesn't exist. Uses a temp file
    in the same directory + os.replace() for atomicity.
    """
    if not cwd:
        raise ValueError("write_task_state requires a non-empty cwd.")
    if content is None:
        content = ""

    path = _state_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file in same directory, then os.replace()
    fd, tmp_path = tempfile.mkstemp(
        prefix=".task-state.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
