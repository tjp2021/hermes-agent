"""Tests for agent/task_state.py — paul-loop durable scratchpad."""
import os
from pathlib import Path

from agent.task_state import (
    read_task_state,
    write_task_state,
    is_paul_loop_active,
    PAUL_LOOP_SENTINEL,
    PAUL_LOOP_RULES,
    TASK_STATE_DIR,
    TASK_STATE_FILE,
)


def test_read_missing_returns_empty(tmp_path):
    assert read_task_state(str(tmp_path)) == ""


def test_write_creates_hermes_dir_and_file(tmp_path):
    write_task_state(str(tmp_path), "hello")
    p = Path(tmp_path) / TASK_STATE_DIR / TASK_STATE_FILE
    assert p.exists()
    assert p.read_text() == "hello"


def test_round_trip(tmp_path):
    content = "## Plan\n- step 1\n- step 2\n"
    write_task_state(str(tmp_path), content)
    assert read_task_state(str(tmp_path)) == content


def test_overwrite_is_atomic(tmp_path):
    write_task_state(str(tmp_path), "v1")
    write_task_state(str(tmp_path), "v2")
    assert read_task_state(str(tmp_path)) == "v2"
    # No stray .tmp left behind
    strays = list((Path(tmp_path) / TASK_STATE_DIR).glob("*.tmp"))
    assert not strays


def test_is_paul_loop_active_detects_sentinel():
    prompt_with = f"... PAUL-LOOP MODE ... {PAUL_LOOP_SENTINEL} ..."
    assert is_paul_loop_active(prompt_with)


def test_is_paul_loop_active_negative():
    assert not is_paul_loop_active("")
    assert not is_paul_loop_active("some other personality")


def test_paul_loop_rules_content():
    # Sanity: rules contain the five numbered operator rules
    for marker in ["1.", "2.", "3.", "4.", "5."]:
        assert marker in PAUL_LOOP_RULES
    assert "ask_user" in PAUL_LOOP_RULES
    assert "rubber_duck" in PAUL_LOOP_RULES
    assert "task-state.md" in PAUL_LOOP_RULES
