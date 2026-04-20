"""Tests for tools/ask_user.py — mandatory turn-end checkpoint."""
import json

from tools.ask_user import ask_user_tool, ASK_USER_SCHEMA


def test_schema_shape():
    assert ASK_USER_SCHEMA["name"] == "ask_user"
    props = ASK_USER_SCHEMA["parameters"]["properties"]
    assert "message" in props
    # free-form: no required choices array
    assert ASK_USER_SCHEMA["parameters"].get("required") == ["message"]


def test_callback_invoked_and_response_returned():
    captured = {}

    def fake_callback(question, choices):
        captured["question"] = question
        captured["choices"] = choices
        return "yes please"

    out = ask_user_tool(message="Proceed with plan?", callback=fake_callback)
    parsed = json.loads(out)
    assert parsed["response"] == "yes please"
    assert captured["question"] == "Proceed with plan?"
    assert captured["choices"] is None


def test_missing_callback_returns_stub():
    out = ask_user_tool(message="hi", callback=None)
    parsed = json.loads(out)
    assert parsed["response"] == ""
    assert "note" in parsed


def test_empty_message_returns_error_json():
    out = ask_user_tool(message="", callback=lambda q, c: "x")
    parsed = json.loads(out)
    assert "error" in parsed


def test_callback_exception_is_caught():
    def bad_cb(q, c):
        raise RuntimeError("ui down")

    out = ask_user_tool(message="q", callback=bad_cb)
    parsed = json.loads(out)
    assert "ui down" in parsed.get("error", "")
