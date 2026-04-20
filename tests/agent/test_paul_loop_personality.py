"""Paul-loop personality registration tests."""
import re

import cli as cli_module
from agent.task_state import PAUL_LOOP_SENTINEL


def test_paul_loop_personality_registered_in_cli_source():
    """The personality dict literal in cli.py must include paul-loop with the sentinel."""
    src = open(cli_module.__file__, "r", encoding="utf-8").read()
    # Personality dict entry present
    assert '"paul-loop"' in src or "'paul-loop'" in src
    # Sentinel embedded in the personality string
    assert PAUL_LOOP_SENTINEL in src


def test_paul_loop_rules_cover_five_primitives():
    from agent.task_state import PAUL_LOOP_RULES
    # Each of the 5 numbered rules appears
    for n in range(1, 6):
        assert re.search(rf"\b{n}\.\s", PAUL_LOOP_RULES), f"Missing rule {n}"
    # Core tool names referenced
    assert "ask_user" in PAUL_LOOP_RULES
    assert "rubber_duck" in PAUL_LOOP_RULES
    assert "delegate_task" in PAUL_LOOP_RULES
    assert "task-state.md" in PAUL_LOOP_RULES
