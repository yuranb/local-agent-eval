"""FastAPI wrapper around the agent loop (scope item 3).

POST /chat runs the full loop and returns the final answer plus a trace of
every tool call it made (tool name, arguments, raw result). The model backend
is injectable so tests can pass a stub instead of real Ollama.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, Request
from pydantic import BaseModel, field_validator

from agent.config import MAX_STEPS, SYSTEM_PROMPT
from agent.loop import run_agent
from agent.tools import TOOL_SCHEMAS


class ChatRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty")
        return value


class ToolCallOut(BaseModel):
    tool: str
    arguments: dict
    result: dict


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallOut]
    steps: int
    error: str | None
    latency_ms: int


def create_app(backend=None) -> FastAPI:
    """Build the app. Pass `backend` to override the model (tests do this);
    otherwise a real OllamaBackend is created on first request."""
    app = FastAPI(title="local-agent-eval")
    app.state.backend = backend

    def get_backend(request: Request):
        if request.app.state.backend is None:
            from agent.llm import OllamaBackend  # imported lazily on purpose

            request.app.state.backend = OllamaBackend()
        return request.app.state.backend

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest, request: Request):
        backend = get_backend(request)
        started = time.perf_counter()
        try:
            result = run_agent(
                payload.question,
                backend,
                tools=TOOL_SCHEMAS,
                system_prompt=SYSTEM_PROMPT,
                max_steps=MAX_STEPS,
            )
        except RuntimeError as exc:  # Ollama unreachable etc.
            return ChatResponse(
                answer="",
                tool_calls=[],
                steps=0,
                error=str(exc),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ChatResponse(
            answer=result.answer,
            tool_calls=[
                ToolCallOut(tool=c["tool"], arguments=c["arguments"], result=c["result"])
                for c in result.tool_calls
            ],
            steps=result.steps,
            error=result.error,
            latency_ms=latency_ms,
        )

    return app


app = create_app()
