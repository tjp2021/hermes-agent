"""Compaction re-anchoring tests (Primitive 5)."""
from pathlib import Path

from agent.task_state import PAUL_LOOP_RULES, PAUL_LOOP_SENTINEL, is_paul_loop_active


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def test_compression_site_reinjects_paul_loop_rules():
    """run_agent.py's compression path must re-inject the paul-loop rules."""
    src = _read("run_agent.py")
    # The post-compression re-anchor references the sentinel AND the rules
    assert "is_paul_loop_active" in src, "re-anchor guard missing"
    assert "PAUL_LOOP_RULES" in src, "re-anchor payload missing"
    # Guarded re-anchor must be near compression code (heuristic: both appear
    # after 'compress(' call site)
    idx_compress = src.find(".compress(")
    idx_rules = src.find("PAUL_LOOP_RULES")
    assert idx_rules > idx_compress, "PAUL_LOOP_RULES must be injected after compress()"


def test_prompt_builder_injects_task_state_under_paul_loop():
    src = _read("run_agent.py")
    # System-prompt build site references task-state injection
    assert "TASK STATE (durable, survives compaction)" in src
    assert "read_task_state" in src


def test_sticky_reminder_every_5_turns_wired():
    src = _read("run_agent.py")
    # Look for the paul-loop sticky-reminder injection
    assert "paul-loop" in src.lower()
    assert "% 5" in src or "%5" in src, "expected a every-5-turn modulo gate"


def test_turn_end_enforcement_wired():
    src = _read("run_agent.py")
    assert "paul-loop violation" in src


def test_is_paul_loop_active_detection():
    # Exact-sentinel positive
    assert is_paul_loop_active(PAUL_LOOP_SENTINEL)
    # Embedded in longer text positive
    assert is_paul_loop_active("foo\n" + PAUL_LOOP_SENTINEL + "\nbar")
    # Negative
    assert not is_paul_loop_active(None)
    assert not is_paul_loop_active("")
    assert not is_paul_loop_active("different personality")


def test_paul_loop_rules_verbatim_match_personality_string():
    """Rules in task_state.PAUL_LOOP_RULES should align with cli.py personality."""
    cli_src = _read("cli.py")
    # Check the spine of the rules appears in cli.py personality string
    for fragment in [
        "DELEGATE EVERYTHING",
        "RUBBER-DUCK EVERY UNIT",
        "END EVERY TURN WITH ask_user",
        "REHYDRATE FROM STATE",
        "NEVER TRUST POST-COMPACTION MEMORY",
    ]:
        assert fragment in cli_src, f"Missing in cli.py personality: {fragment}"
        assert fragment in PAUL_LOOP_RULES, f"Missing in PAUL_LOOP_RULES: {fragment}"
