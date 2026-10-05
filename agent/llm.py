"""Ollama chat backend (DECISIONS.md D9).

A deliberately thin client: one POST to /api/chat with stream=false. The only
logic worth testing is `normalize_message`, which papers over the fact that
some Ollama versions return tool-call arguments as a JSON string instead of
an object.
"""
from __future__ import annotations

import json

import httpx

from .config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS


def normalize_message(message: dict) -> dict:
    """Return an assistant message with tool_calls in a predictable shape.

    Guarantees: role is "assistant", content is always a str, and every tool
    call looks like {"function": {"name": str, "arguments": dict}}.
    """
    normalized = {
        "role": "assistant",
        "content": message.get("content") or "",
    }
    tool_calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {}) or {}
        arguments = fn.get("arguments", {})
        if isinstance(arguments, str):
            arguments = json.loads(arguments) if arguments.strip() else {}
        tool_calls.append(
            {"function": {"name": fn.get("name"), "arguments": arguments or {}}}
        )
    if tool_calls:
        normalized["tool_calls"] = tool_calls
    return normalized


class OllamaBackend:
    """Talks to a local Ollama server. Requires `ollama serve` to be running."""

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        host: str = OLLAMA_HOST,
        timeout: float = OLLAMA_TIMEOUT_SECONDS,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Send the conversation, get back one normalized assistant message."""
        payload: dict = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        try:
            response = httpx.post(
                f"{self.host}/api/chat", json=payload, timeout=self.timeout
            )
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"cannot reach Ollama at {self.host} — is it installed and "
                "running? (This machine had no Ollama; see STATUS.md.)"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Ollama at {self.host} did not answer within {self.timeout}s — "
                "the server may be busy with other requests (raise OLLAMA_TIMEOUT "
                "or wait for the other load to finish)."
            ) from exc
        response.raise_for_status()
        return normalize_message(response.json()["message"])
