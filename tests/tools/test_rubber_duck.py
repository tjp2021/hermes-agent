"""Tests for tools/rubber_duck.py — parallel multi-model critique."""
import json

from tools.rubber_duck import rubber_duck, RUBBER_DUCK_SCHEMA, DEFAULT_CRITICS


def _mock_delegate_factory(critic_payloads):
    """Build a fake delegate_task that returns a canned envelope."""
    captured = {"calls": 0, "tasks": None}

    def fake_delegate(tasks=None, parent_agent=None, **kwargs):
        captured["calls"] += 1
        captured["tasks"] = tasks
        return json.dumps({
            "results": [
                {"summary": payload} for payload in critic_payloads
            ],
        })

    return fake_delegate, captured


def test_schema_shape():
    assert RUBBER_DUCK_SCHEMA["name"] == "rubber_duck"
    req = RUBBER_DUCK_SCHEMA["parameters"]["required"]
    assert "artifact" in req and "unit_description" in req


def test_convergence_when_all_clean():
    payloads = [
        '{"verdict": "clean", "issues": []}',
        '{"verdict": "clean", "issues": []}',
    ]
    fake, captured = _mock_delegate_factory(payloads)
    out = rubber_duck(
        artifact="def f(): pass",
        unit_description="trivial fn",
        parent_agent=object(),
        _delegate_task_fn=fake,
    )
    parsed = json.loads(out)
    assert parsed["status"] == "converged"
    assert parsed["round"] == 1
    # Parallel spawn: one delegate_task call with N tasks
    assert captured["calls"] == 1
    assert len(captured["tasks"]) == len(DEFAULT_CRITICS)


def test_changes_requested_when_any_critic_flags():
    payloads = [
        '{"verdict": "clean", "issues": []}',
        '{"verdict": "changes_needed", "issues": [{"severity": "high", "location": "L1", "fix": "rename var"}]}',
    ]
    fake, _ = _mock_delegate_factory(payloads)
    out = rubber_duck(
        artifact="x=1",
        unit_description="assign",
        parent_agent=object(),
        _delegate_task_fn=fake,
    )
    parsed = json.loads(out)
    assert parsed["status"] == "changes_requested"
    assert len(parsed["critiques"]) == 2


def test_round_counter_increments_explicitly():
    payloads = ['{"verdict": "clean", "issues": []}'] * 2
    fake, _ = _mock_delegate_factory(payloads)
    out = rubber_duck(
        artifact="ok",
        unit_description="u",
        round=3,
        parent_agent=object(),
        _delegate_task_fn=fake,
    )
    parsed = json.loads(out)
    assert parsed["round"] == 3


def test_max_rounds_exceeded():
    payloads = ['{"verdict": "changes_needed", "issues":[{"severity":"low","location":"x","fix":"y"}]}'] * 2
    fake, _ = _mock_delegate_factory(payloads)
    out = rubber_duck(
        artifact="ok",
        unit_description="u",
        round=5,
        max_rounds=5,
        parent_agent=object(),
        _delegate_task_fn=fake,
    )
    parsed = json.loads(out)
    assert parsed["status"] == "max_rounds_exceeded"


def test_parallel_task_count_matches_critics():
    payloads = ['{"verdict":"clean","issues":[]}'] * 3
    fake, captured = _mock_delegate_factory(payloads)
    rubber_duck(
        artifact="ok",
        unit_description="u",
        critics=["a", "b", "c"],
        parent_agent=object(),
        _delegate_task_fn=fake,
    )
    assert len(captured["tasks"]) == 3


def test_missing_artifact_errors():
    out = rubber_duck(
        artifact="",
        unit_description="u",
        parent_agent=object(),
        _delegate_task_fn=lambda **kw: "{}",
    )
    assert "error" in json.loads(out)


def test_missing_parent_agent_errors():
    out = rubber_duck(
        artifact="x",
        unit_description="u",
        parent_agent=None,
        _delegate_task_fn=lambda **kw: "{}",
    )
    assert "error" in json.loads(out)
