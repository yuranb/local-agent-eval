"""Run the whole eval over evals/cases.jsonl and write a results JSON.

Backends:
  --backend recording  replay recorded/fixture model responses (works in CI)
  --backend ollama     hit a real local Ollama server

Output JSON contains per-case scoring plus aggregate metrics; evals/gate.py
compares a results file against evals/baseline.json (scope item 7).
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.config import OLLAMA_MODEL
from agent.loop import run_agent
from agent.tools import TOOL_SCHEMAS
from evals.recording import RecordingBackend, load_recordings
from evals.scoring import compute_metrics, score_case

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "evals" / "cases.jsonl"
DEFAULT_RECORDINGS = ROOT / "evals" / "recordings"

METRICS_FILE_VERSION = 1


def load_cases(cases_path: Path = DEFAULT_CASES) -> list:
    cases = []
    with Path(cases_path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    if not cases:
        raise ValueError(f"no cases found in {cases_path}")
    return cases


def run_eval(cases: list, backend_for_case, label: str, model: str | None) -> dict:
    scored = []
    for case in cases:
        backend = backend_for_case(case)
        started = time.perf_counter()
        try:
            result = run_agent(case["question"], backend, tools=TOOL_SCHEMAS)
        except Exception as exc:  # noqa: BLE001 - a backend crash is a failed case
            from agent.loop import AgentResult

            result = AgentResult(answer="", steps=0, error=f"backend failure: {exc}")
        latency_ms = int((time.perf_counter() - started) * 1000)
        scored.append(score_case(case, result, latency_ms))

    return {
        "schema_version": METRICS_FILE_VERSION,
        "backend": label,
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": compute_metrics(scored),
        "cases": scored,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["recording", "ollama"], default="recording")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--recordings-dir", type=Path, default=DEFAULT_RECORDINGS)
    parser.add_argument("--model", default=None, help="Ollama model name (ollama backend)")
    parser.add_argument("--out", type=Path, required=True, help="Where to write results JSON")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)

    if args.backend == "recording":
        recordings = load_recordings(args.recordings_dir)
        missing = [c["id"] for c in cases if c["id"] not in recordings]
        if missing:
            print(f"ERROR: no recording for {len(missing)} cases, e.g. {missing[:3]}")
            return 2

        def backend_for_case(case):
            rec = recordings[case["id"]]
            return RecordingBackend(case["id"], rec["turns"], rec.get("source", "fixture"))

        label, model = "recording", None
    else:
        from agent.llm import OllamaBackend

        shared = OllamaBackend(model=args.model or OLLAMA_MODEL)

        def backend_for_case(case):
            return shared

        label, model = "ollama", args.model or OLLAMA_MODEL

    report = run_eval(cases, backend_for_case, label, model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    m = report["metrics"]
    print(f"cases: {m['total_cases']}")
    print(f"tool_selection_accuracy: {m['tool_selection_accuracy']:.3f}")
    print(f"argument_accuracy:       {m['argument_accuracy']:.3f}")
    print(f"answer_accuracy:         {m['answer_accuracy']:.3f}")
    print(f"latency p50/p95 (ms):    {m['latency_ms_p50']} / {m['latency_ms_p95']}")
    print(f"wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
