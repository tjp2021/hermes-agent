#!/usr/bin/env python3
"""
Rubber-Duck Tool — Parallel Multi-Model Critique Loop

Intent: every unit of work (plan, draft, code change) under `paul-loop`
personality gets critiqued by N parallel peer models. Rubber-duck returns
after ONE round; the calling agent applies the agreed fixes and re-invokes
rubber_duck until verdicts converge.

This is deliberately not a blocking internal loop — returning after each
round is what lets the main agent actually APPLY critiques between rounds.

Under the hood we reuse `delegate_task`'s batch mode to spawn the critic
subagents in parallel. All critics currently inherit the parent model;
the `critics` list is used as a *critique persona* label passed to each
subagent so different critic identities can emerge even with shared
inference infra. Future work: true per-critic model routing.
"""

import json
from typing import Any, Callable, Dict, List, Optional


DEFAULT_CRITICS = ["anthropic/claude-opus-4.7", "openai/gpt-5.4"]
DEFAULT_MAX_ROUNDS = 5


_CRITIQUE_PROMPT_TEMPLATE = """You are acting as a code/artifact critic under persona `{critic}`.

You are one of several parallel reviewers. Be direct, specific, and
actionable. Do NOT be polite-filler — point out real issues only.

Unit of work being critiqued: {unit_description}

Artifact:
---
{artifact}
---

Return ONLY a single JSON object (no prose before or after) with this shape:
{{
  "issues": [
    {{"severity": "low|medium|high", "location": "<where>", "fix": "<concrete fix>"}}
  ],
  "verdict": "clean" | "changes_needed"
}}

If the artifact is solid, return verdict="clean" with issues=[].
"""


def _parse_critic_response(raw: str) -> Dict[str, Any]:
    """Best-effort extraction of the JSON critique from a subagent response."""
    if not raw:
        return {"verdict": "changes_needed", "issues": [
            {"severity": "medium", "location": "(critic)",
             "fix": "Critic returned empty response."}
        ]}
    text = raw.strip()
    # Locate the first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        snippet = text[start:end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {"verdict": "changes_needed", "issues": [
        {"severity": "low", "location": "(parser)",
         "fix": f"Could not parse critic JSON. Raw: {text[:300]}"}
    ]}


def rubber_duck(
    artifact: str,
    unit_description: str,
    critics: Optional[List[str]] = None,
    max_rounds: Optional[int] = None,
    round: Optional[int] = None,
    parent_agent=None,
    _delegate_task_fn: Optional[Callable] = None,
) -> str:
    """
    Run ONE round of multi-critic critique. The calling agent is expected
    to apply fixes and then re-invoke rubber_duck with round+=1.

    Returns a JSON string — see CONTRACT in RUBBER_DUCK_SCHEMA.
    """
    if not artifact or not str(artifact).strip():
        return tool_error("artifact is required.")
    if not unit_description or not str(unit_description).strip():
        return tool_error("unit_description is required.")

    artifact = str(artifact)
    unit_description = str(unit_description).strip()
    critic_list = list(critics) if critics else list(DEFAULT_CRITICS)
    if not critic_list:
        critic_list = list(DEFAULT_CRITICS)

    max_rounds_eff = int(max_rounds) if max_rounds else DEFAULT_MAX_ROUNDS
    current_round = int(round) if round else 1

    if current_round > max_rounds_eff:
        return json.dumps({
            "status": "max_rounds_exceeded",
            "round": current_round,
            "max_rounds": max_rounds_eff,
            "critiques": [],
        }, ensure_ascii=False)

    # Resolve delegate_task (allow test injection)
    if _delegate_task_fn is None:
        try:
            from tools.delegate_tool import delegate_task as _delegate_task_fn
        except Exception as exc:
            return tool_error(f"Could not load delegate_task: {exc}")

    if parent_agent is None:
        return tool_error("rubber_duck requires a parent agent context.")

    # Build parallel critic tasks
    tasks = []
    for critic in critic_list:
        tasks.append({
            "goal": _CRITIQUE_PROMPT_TEMPLATE.format(
                critic=critic,
                unit_description=unit_description,
                artifact=artifact,
            ),
            "context": f"You are critic persona: {critic}. Round {current_round}/{max_rounds_eff}.",
        })

    try:
        raw_delegate = _delegate_task_fn(
            tasks=tasks,
            parent_agent=parent_agent,
        )
    except Exception as exc:
        return tool_error(f"delegate_task raised: {exc}")

    # Parse the delegate_task envelope
    try:
        delegate_payload = json.loads(raw_delegate) if isinstance(raw_delegate, str) else raw_delegate
    except Exception:
        delegate_payload = {}

    results = (delegate_payload or {}).get("results") or []

    critiques: List[Dict[str, Any]] = []
    all_clean = True
    for critic, entry in zip(critic_list, results):
        summary = ""
        if isinstance(entry, dict):
            summary = entry.get("summary") or entry.get("final_response") or ""
        parsed = _parse_critic_response(summary)
        verdict = parsed.get("verdict", "changes_needed")
        issues = parsed.get("issues") or []
        if verdict != "clean" or issues:
            all_clean = False
        critiques.append({
            "critic": critic,
            "verdict": verdict,
            "issues": issues,
        })

    if all_clean and critiques:
        status = "converged"
    elif current_round >= max_rounds_eff:
        status = "max_rounds_exceeded"
    else:
        status = "changes_requested"

    return json.dumps({
        "status": status,
        "round": current_round,
        "max_rounds": max_rounds_eff,
        "critiques": critiques,
        "next_round_hint": (
            f"Apply the critiques above, then re-call rubber_duck with round={current_round + 1}."
            if status == "changes_requested" else ""
        ),
    }, ensure_ascii=False)


def check_rubber_duck_requirements() -> bool:
    """Rubber-duck is available whenever delegate_task is available."""
    try:
        import tools.delegate_tool  # noqa: F401
        return True
    except Exception:
        return False


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

RUBBER_DUCK_SCHEMA = {
    "name": "rubber_duck",
    "description": (
        "Run ONE round of parallel multi-model critique on a unit of work "
        "(plan, draft, code change). Returns critiques from N critic subagents.\n\n"
        "CONTRACT: This tool executes exactly one round, then returns. The "
        "calling agent MUST apply fixes (or decide to ignore critiques) and "
        "then re-call rubber_duck with `round` incremented until the response "
        "has `status: 'converged'` or `status: 'max_rounds_exceeded'`.\n\n"
        "Returned statuses:\n"
        "  - converged          — all critics returned verdict='clean' / no issues\n"
        "  - changes_requested  — at least one critic flagged issues; apply + re-call\n"
        "  - max_rounds_exceeded — budget hit; surface to user via ask_user\n\n"
        "Use this for every material unit of work under paul-loop personality."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "string",
                "description": "The artifact to critique — code, plan text, draft, etc.",
            },
            "unit_description": {
                "type": "string",
                "description": "One-line description of what this unit of work is.",
            },
            "critics": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of critic persona labels (usually model strings). "
                    f"Default: {DEFAULT_CRITICS}"
                ),
            },
            "max_rounds": {
                "type": "integer",
                "description": f"Max critique rounds before giving up. Default: {DEFAULT_MAX_ROUNDS}",
            },
            "round": {
                "type": "integer",
                "description": "Current round number (default 1). Increment on re-call.",
            },
        },
        "required": ["artifact", "unit_description"],
    },
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="rubber_duck",
    toolset="rubber_duck",
    schema=RUBBER_DUCK_SCHEMA,
    handler=lambda args, **kw: rubber_duck(
        artifact=args.get("artifact", ""),
        unit_description=args.get("unit_description", ""),
        critics=args.get("critics"),
        max_rounds=args.get("max_rounds"),
        round=args.get("round"),
        parent_agent=kw.get("parent_agent"),
    ),
    check_fn=check_rubber_duck_requirements,
    emoji="🦆",
)
