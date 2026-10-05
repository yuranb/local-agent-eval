"""Tests for the agent loop using a scripted stub backend — no Ollama needed."""
import pytest

from agent.loop import AgentResult, run_agent


class StubBackend:
    """Returns pre-scripted assistant messages, one per chat() call."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []  # snapshots of (messages, tools) per chat() call

    def chat(self, messages, tools=None):
        self.calls.append((list(messages), tools))
        if not self.turns:
            raise AssertionError("StubBackend ran out of scripted turns")
        return self.turns.pop(0)


def tool_call(name, **arguments):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def test_loop_answers_directly_without_tools():
    backend = StubBackend([{"role": "assistant", "content": "Hello!"}])
    result = run_agent("Say hello", backend)
    assert result.answer == "Hello!"
    assert result.tool_calls == []
    assert result.steps == 1
    assert result.error is None


def test_loop_executes_tool_and_feeds_result_back():
    backend = StubBackend([
        tool_call("calculator", expression="2+2"),
        {"role": "assistant", "content": "The answer is 4."},
    ])
    result = run_agent("What is 2+2?", backend)

    assert result.answer == "The answer is 4."
    assert result.tool_calls == [
        {"tool": "calculator", "arguments": {"expression": "2+2"}, "result": {"expression": "2+2", "value": 4}}
    ]
    assert result.steps == 2

    # The second model turn must contain the tool result as a role="tool" message.
    second_messages, _ = backend.calls[1]
    tool_messages = [m for m in second_messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert '"value": 4' in tool_messages[0]["content"]


def test_loop_handles_multiple_tool_calls_in_one_turn():
    backend = StubBackend([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "calculator", "arguments": {"expression": "1+1"}}},
            {"function": {"name": "calculator", "arguments": {"expression": "3*3"}}},
        ]},
        {"role": "assistant", "content": "2 and 9."},
    ])
    result = run_agent("two maths", backend)
    assert result.tools_used() == ["calculator", "calculator"]
    assert [c["result"]["value"] for c in result.tool_calls] == [2, 9]


def test_loop_survives_tool_failure_and_reports_it_to_model():
    backend = StubBackend([
        tool_call("calculator", expression="1/0"),
        {"role": "assistant", "content": "That division is undefined."},
    ])
    result = run_agent("divide by zero", backend)
    assert result.tool_calls[0]["result"] == {"error": "division by zero"}
    # The model saw the error text.
    tool_messages = [m for m in backend.calls[1][0] if m["role"] == "tool"]
    assert "division by zero" in tool_messages[0]["content"]
    assert result.error is None


def test_loop_stops_after_max_steps():
    endless = tool_call("calculator", expression="1+1")
    backend = StubBackend([endless] * 10)
    result = run_agent("looping forever", backend, max_steps=3)
    assert result.answer == ""
    assert result.error is not None
    assert "3 steps" in result.error
    assert result.steps == 3
    assert len(backend.calls) == 3


def test_loop_passes_tool_schemas_to_backend():
    backend = StubBackend([{"role": "assistant", "content": "ok"}])
    run_agent("hi", backend)
    _, tools = backend.calls[0]
    assert tools is not None and len(tools) == 3


def test_loop_starts_with_system_and_user_messages():
    backend = StubBackend([{"role": "assistant", "content": "ok"}])
    run_agent("hi", backend, system_prompt="BE BRIEF")
    messages, _ = backend.calls[0]
    assert messages[0] == {"role": "system", "content": "BE BRIEF"}
    assert messages[1] == {"role": "user", "content": "hi"}


def test_agent_result_tools_used_reflects_call_order():
    res = AgentResult(answer="", tool_calls=[
        {"tool": "search_docs", "arguments": {}, "result": {}},
        {"tool": "calculator", "arguments": {}, "result": {}},
        {"tool": "search_docs", "arguments": {}, "result": {}},
    ])
    assert res.tools_used() == ["search_docs", "calculator", "search_docs"]
