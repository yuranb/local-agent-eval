"""The agent loop: model <-> tools until the model produces a final answer.

This is the heart of the project. A "backend" is anything with a
`chat(messages, tools) -> assistant-message-dict` method, so the same loop
runs against real Ollama, recorded responses, or a test stub (DECISIONS.md D3).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .config import MAX_STEPS, SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, execute_tool


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[dict] = field(default_factory=list)
    steps: int = 0
    error: str | None = None

    def tools_used(self) -> list[str]:
        """Names of the tools that were called, in call order, with repeats."""
        return [call["tool"] for call in self.tool_calls]


def run_agent(
    question: str,
    backend,
    tools: list[dict] | None = TOOL_SCHEMAS,
    system_prompt: str = SYSTEM_PROMPT,
    max_steps: int = MAX_STEPS,
) -> AgentResult:
    """Ask `question`, let the model call tools, return the final result.

    One "step" is one model turn. Tool results go back to the model as
    role="tool" messages (JSON-encoded). Tool failures become {"error": ...}
    observations instead of exceptions (DECISIONS.md D8). If the model still
    has not answered after max_steps, we stop with an error flag rather than
    loop forever.
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    trace: list[dict] = []

    for step in range(1, max_steps + 1):
        message = backend.chat(messages, tools)

        tool_requests = message.get("tool_calls") or []
        if not tool_requests:
            return AgentResult(
                answer=message.get("content", ""),
                tool_calls=trace,
                steps=step,
            )

        messages.append(message)
        for request in tool_requests:
            name = request["function"]["name"]
            arguments = request["function"]["arguments"]
            result = execute_tool(name, arguments)
            trace.append({"tool": name, "arguments": arguments, "result": result})
            messages.append({"role": "tool", "content": json.dumps(result)})

    return AgentResult(
        answer="",
        tool_calls=trace,
        steps=max_steps,
        error=f"model did not produce a final answer within {max_steps} steps",
    )
