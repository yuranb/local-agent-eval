"""Record real Ollama responses per eval case, for the CI gate to replay.

Run this on a machine with Ollama installed (see STATUS.md: this machine has
none, so this script has never been executed). It runs the same agent loop as
the eval but captures every assistant message instead of discarding it:

    python -m evals.record --model qwen2.5:7b
    python -m evals.run_eval --backend recording --out evals/baseline.json

The recordings then contain genuine model behaviour, and baseline.json
becomes a real model-quality gate instead of a pipeline regression gate.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from agent.config import OLLAMA_MODEL
from agent.loop import run_agent
from agent.tools import TOOL_SCHEMAS
from evals.run_eval import DEFAULT_CASES, DEFAULT_RECORDINGS, load_cases


class CapturingBackend:
    """Wraps any backend and records every assistant message it returns."""

    def __init__(self, inner):
        self.inner = inner
        self.captured: list = []

    def chat(self, messages, tools=None):
        message = self.inner.chat(messages, tools)
        self.captured.append(message)
        return message


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=OLLAMA_MODEL)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_RECORDINGS)
    args = parser.parse_args(argv)

    from agent.llm import OllamaBackend  # only imported if actually used

    ollama = OllamaBackend(model=args.model)
    cases = load_cases(args.cases)
    failures = []

    for case in cases:
        backend = CapturingBackend(ollama)
        result = run_agent(case["question"], backend, tools=TOOL_SCHEMAS)
        payload = {
            "case_id": case["id"],
            "source": f"ollama:{args.model}",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "final_error": result.error,
            "turns": backend.captured,
        }
        out_path = args.out_dir / f"{case['id']}.json"
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        status = "ok" if result.error is None else f"error: {result.error}"
        print(f"{case['id']}: {len(backend.captured)} turns, {status}")
        if result.error is not None:
            failures.append(case["id"])

    if failures:
        print(f"\n{len(failures)} cases did not finish cleanly: {failures}")
        return 1
    print(f"\nrecorded all {len(cases)} cases into {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
