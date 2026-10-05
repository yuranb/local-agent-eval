"""Tests for the pure parts of agent/llm.py (no HTTP calls)."""
import json

import pytest

from agent.llm import OllamaBackend, normalize_message


def test_normalize_message_plain_answer():
    msg = normalize_message({"role": "assistant", "content": "hi"})
    assert msg == {"role": "assistant", "content": "hi"}


def test_normalize_message_missing_content_becomes_empty_string():
    msg = normalize_message({"role": "assistant", "tool_calls": []})
    assert msg["content"] == ""
    assert "tool_calls" not in msg


def test_normalize_message_object_arguments_pass_through():
    raw = {"content": "", "tool_calls": [
        {"function": {"name": "calculator", "arguments": {"expression": "1+1"}}}
    ]}
    msg = normalize_message(raw)
    assert msg["tool_calls"][0]["function"]["arguments"] == {"expression": "1+1"}


def test_normalize_message_string_arguments_are_decoded():
    raw = {"content": "", "tool_calls": [
        {"function": {"name": "calculator",
                      "arguments": json.dumps({"expression": "1+1"})}}
    ]}
    msg = normalize_message(raw)
    assert msg["tool_calls"][0]["function"]["arguments"] == {"expression": "1+1"}


def test_normalize_message_empty_string_arguments_become_empty_dict():
    raw = {"content": "", "tool_calls": [{"function": {"name": "x", "arguments": ""}}]}
    assert normalize_message(raw)["tool_calls"][0]["function"]["arguments"] == {}


def test_normalize_message_null_arguments_become_empty_dict():
    raw = {"content": "", "tool_calls": [{"function": {"name": "x", "arguments": None}}]}
    assert normalize_message(raw)["tool_calls"][0]["function"]["arguments"] == {}


def test_ollama_backend_default_config_from_env():
    backend = OllamaBackend()
    assert backend.model == "qwen2.5:7b"
    assert backend.host == "http://localhost:11434"


def test_ollama_backend_strips_trailing_slash_from_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:9999/")
    import importlib
    import agent.config as config
    importlib.reload(config)
    from agent import llm as llm_module
    importlib.reload(llm_module)
    backend = llm_module.OllamaBackend(host=config.OLLAMA_HOST)
    assert backend.host == "http://localhost:9999"


def test_ollama_backend_translates_connect_error(monkeypatch):
    backend = OllamaBackend(host="http://localhost:1")
    import httpx as httpx_module

    def raise_connect_error(*args, **kwargs):
        raise httpx_module.ConnectError("nope")

    monkeypatch.setattr(httpx_module, "post", raise_connect_error)
    with pytest.raises(RuntimeError, match="Ollama"):
        backend.chat([{"role": "user", "content": "hi"}])
