"""Central configuration. Everything is overridable by environment variables
so the same code runs on the laptop and in CI without edits."""
from __future__ import annotations

import os

# Default model. See DECISIONS.md D2: qwen2.5:7b (7.6B, native tool calling,
# Apache-2.0) is the intended choice, but this machine has no Ollama installed
# so it has never been verified — swap freely via OLLAMA_MODEL.
# Alternative with mature tool-calling support: "llama3.1:8b".
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# Ollama's local HTTP endpoint (DECISIONS.md D9).
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Hard stop for the tool-calling loop so a confused model cannot spin forever.
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "5"))

# Generous timeout: small models on a laptop can take a while per turn.
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT", "120"))

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to local tools.\n"
    "Rules:\n"
    "1. If the question asks about the content of documents, call search_docs.\n"
    "2. If it requires any arithmetic or date math, call calculator or "
    "add_workdays instead of computing in your head.\n"
    "3. If no tool is needed, just answer directly in one or two sentences.\n"
    "4. After using a tool, give the final answer in the same turn as soon as "
    "you have everything you need."
)
