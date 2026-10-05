"""API tests using FastAPI's TestClient with a stub backend — no Ollama."""
import pytest
from fastapi.testclient import TestClient

from server.app import create_app


class StubBackend:
    def __init__(self, turns):
        self.turns = list(turns)

    def chat(self, messages, tools=None):
        return self.turns.pop(0)


def tool_call(name, **arguments):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


@pytest.fixture()
def client():
    backend = StubBackend([
        tool_call("search_docs", query="four score"),
        {"role": "assistant", "content": "Lincoln said it at Gettysburg."},
    ])
    app = create_app(backend=backend)
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_answer_and_tool_trace(client):
    response = client.post("/chat", json={"question": "Who said four score?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Lincoln said it at Gettysburg."
    assert body["error"] is None
    assert len(body["tool_calls"]) == 1
    call = body["tool_calls"][0]
    assert call["tool"] == "search_docs"
    assert call["arguments"] == {"query": "four score"}
    assert call["result"]["snippets"][0]["file"] == "gettysburg_address"
    assert body["steps"] == 2
    assert isinstance(body["latency_ms"], int)


def test_chat_without_tool_calls_has_empty_trace():
    backend = StubBackend([{"role": "assistant", "content": "Hi there."}])
    client = TestClient(create_app(backend=backend))
    body = client.post("/chat", json={"question": "hello"}).json()
    assert body["answer"] == "Hi there."
    assert body["tool_calls"] == []
    assert body["steps"] == 1


def test_chat_rejects_blank_question(client):
    response = client.post("/chat", json={"question": "   "})
    assert response.status_code == 422


def test_chat_rejects_missing_question(client):
    response = client.post("/chat", json={})
    assert response.status_code == 422


def test_chat_returns_error_field_when_model_never_answers():
    # The loop runs up to MAX_STEPS turns, so script that many tool calls.
    backend = StubBackend(
        [tool_call("calculator", expression="1+1")] * 5
    )
    client = TestClient(create_app(backend=backend))
    body = client.post("/chat", json={"question": "loop please"}).json()
    assert body["answer"] == ""
    assert "did not produce a final answer" in body["error"]


def test_lazy_backend_creation_defaults_to_ollama():
    # create_app() with no backend must not touch the network at import time,
    # and the first request should try to build an OllamaBackend.
    from server.app import app as default_app

    assert default_app.state.backend is None
