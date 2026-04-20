"""Tests for config-driven Telegram lane routing."""

import asyncio
import importlib
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource


class _CapturingAgent:
    last_init = None

    def __init__(self, *args, **kwargs):
        type(self).last_init = dict(kwargs)
        self.tools = []
        self.context_cwd = kwargs.get("context_cwd")

    def run_conversation(self, message, conversation_history=None, task_id=None):
        return {
            "final_response": "ok",
            "messages": [],
            "api_calls": 1,
        }


def _make_lane_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.TELEGRAM: PlatformConfig(
                enabled=True,
                token="***",
                extra={
                    "lane_mappings": [
                        {
                            "chat_id": "-100123",
                            "name": "OG",
                            "cwd": "~/YNG/01_business/og",
                            "prompt": "OG-owned systems only.",
                        }
                    ]
                },
            )
        }
    )
    runner.adapters = {}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = SessionEntry(
        session_key="agent:main:telegram:group:-100123",
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="group",
    )
    runner.session_store.load_transcript.return_value = []
    runner.session_store.has_any_sessions.return_value = True
    runner.session_store.append_to_transcript = MagicMock()
    runner.session_store.update_session = MagicMock()
    runner.session_store.rewrite_transcript = MagicMock()
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._session_db = None
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._show_reasoning = False
    runner._is_user_authorized = lambda _source: True
    runner._set_session_env = lambda _context: None
    runner._should_send_voice_reply = lambda *_args, **_kwargs: False
    runner._send_voice_reply = AsyncMock()
    return runner


@pytest.mark.asyncio
async def test_handle_message_injects_lane_prompt_and_cwd():
    runner = _make_lane_runner()
    runner._run_agent = AsyncMock(
        return_value={
            "final_response": "ok",
            "messages": [],
            "tools": [],
            "history_offset": 0,
            "last_prompt_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "model": "openrouter/test-model",
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
        }
    )

    result = await runner._handle_message(
        MessageEvent(
            text="hello",
            source=SessionSource(
                platform=Platform.TELEGRAM,
                chat_id="-100123",
                chat_type="group",
            ),
            message_id="m1",
        )
    )

    assert result == "ok"
    kwargs = runner._run_agent.call_args.kwargs
    assert kwargs["lane_cwd"].endswith("/YNG/01_business/og")
    assert "## Lane Binding" in kwargs["context_prompt"]
    assert "**Lane:** OG" in kwargs["context_prompt"]
    assert "OG-owned systems only." in kwargs["context_prompt"]


@pytest.mark.asyncio
async def test_run_agent_registers_lane_cwd_for_agent_and_tools(monkeypatch, tmp_path):
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = _CapturingAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    gateway_run = importlib.import_module("gateway.run")
    GatewayRunner = gateway_run.GatewayRunner

    registered = []
    cleared = []

    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})
    monkeypatch.setattr(gateway_run, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "tools.register_task_env_overrides",
        lambda task_id, overrides: registered.append((task_id, dict(overrides))),
    )
    monkeypatch.setattr(
        "tools.clear_task_env_overrides",
        lambda task_id: cleared.append(task_id),
    )

    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._voice_mode = {}
    runner._prefill_messages = []
    runner._ephemeral_system_prompt = ""
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._session_db = None
    runner._running_agents = {}
    runner._agent_cache = {}
    runner._agent_cache_lock = MagicMock()
    runner.hooks = SimpleNamespace(loaded_hooks=False)
    runner._get_or_create_gateway_honcho = lambda session_key: (None, None)

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="-100123",
        chat_type="group",
    )

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-1",
        session_key="agent:main:telegram:group:-100123",
        lane_cwd="/tmp/og-lane",
    )

    assert result["final_response"] == "ok"
    assert _CapturingAgent.last_init is not None
    assert _CapturingAgent.last_init["context_cwd"] == "/tmp/og-lane"
    assert registered == [("sess-1", {"cwd": "/tmp/og-lane"})]
    assert cleared == ["sess-1"]
