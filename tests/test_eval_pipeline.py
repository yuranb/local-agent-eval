"""End-to-end tests for the eval pipeline: run_eval on fixture recordings,
plus the gate — all on temporary directories, never touching real Ollama."""
import json

import pytest

from evals.gate import compare
from evals.make_recordings import build_turns
from evals.recording import RecordingBackend, load_recordings
from evals.run_eval import load_cases, run_eval


# --------------------------------------------------------------------------
# make_recordings.build_turns
# --------------------------------------------------------------------------

def test_build_turns_for_tool_case_starts_with_expected_call():
    from evals.run_eval import load_cases

    case = next(c for c in load_cases() if c["id"] == "calc-001")
    turns = build_turns(case)
    assert turns[0]["tool_calls"][0]["function"] == {
        "name": "calculator",
        "arguments": {"expression": "12*12"},
    }
    assert "144" in turns[-1]["content"]


def test_build_turns_for_no_tool_case_has_single_answer_turn():
    from evals.run_eval import load_cases

    case = next(c for c in load_cases() if c["id"] == "notool-002")
    turns = build_turns(case)
    assert len(turns) == 1
    assert "Mars" in turns[0]["content"]


def test_every_dataset_case_yields_a_replayable_fixture():
    cases = load_cases()
    for case in cases:
        turns = build_turns(case)  # raises if fixture cannot satisfy its rule
        final = turns[-1]["content"]
        assert final, f"{case['id']} has an empty final answer"


# --------------------------------------------------------------------------
# recording backend
# --------------------------------------------------------------------------

def test_recording_backend_replays_turns_in_order():
    turns = [{"role": "assistant", "content": "a"}, {"role": "assistant", "content": "b"}]
    backend = RecordingBackend("x", turns)
    assert backend.chat([], None)["content"] == "a"
    assert backend.chat([], None)["content"] == "b"


def test_recording_backend_raises_when_exhausted():
    backend = RecordingBackend("x", [])
    with pytest.raises(RuntimeError, match="exhausted"):
        backend.chat([], None)


def test_load_recordings_reads_directory(tmp_path):
    (tmp_path / "a.json").write_text(
        json.dumps({"case_id": "a", "source": "fixture", "turns": [1]}), encoding="utf-8"
    )
    recordings = load_recordings(tmp_path)
    assert recordings["a"]["turns"] == [1]


# --------------------------------------------------------------------------
# run_eval end to end on fixtures
# --------------------------------------------------------------------------

def test_run_eval_recording_backend_perfect_on_fixtures(tmp_path):
    # Build fresh fixture recordings in a temp dir instead of reading
    # evals/recordings/ — that directory holds real model recordings now,
    # whose metrics are whatever the model actually achieved.
    from evals.make_recordings import NOTE
    import json as json_module

    cases = load_cases()
    for case in cases:
        payload = {
            "case_id": case["id"],
            "source": "fixture",
            "note": NOTE,
            "turns": build_turns(case),
        }
        (tmp_path / f"{case['id']}.json").write_text(
            json_module.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    recordings = load_recordings(tmp_path)

    def backend_for_case(case):
        rec = recordings[case["id"]]
        return RecordingBackend(case["id"], rec["turns"], rec["source"])

    report = run_eval(cases, backend_for_case, "recording", None)
    assert report["metrics"]["total_cases"] == 50
    assert report["metrics"]["tool_selection_accuracy"] == 1.0
    assert report["metrics"]["argument_accuracy"] == 1.0
    assert report["metrics"]["answer_accuracy"] == 1.0
    assert len(report["cases"]) == 50
    # latency must be real measured ints
    assert all(isinstance(c["latency_ms"], int) for c in report["cases"])


def test_run_eval_scores_failure_when_recording_is_wrong(tmp_path):
    case = {"id": "t1", "category": "calculator", "question": "q",
            "expected_tools": ["calculator"],
            "expected_args": {"calculator": {"expression": "1+1"}},
            "answer_rule": {"type": "contains", "value": "2"}}
    # Model calls the WRONG tool, then answers wrongly.
    turns = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "search_docs", "arguments": {"query": "1+1"}}}]},
        {"role": "assistant", "content": "no idea"},
    ]

    report = run_eval([case], lambda c: RecordingBackend("t1", turns), "recording", None)
    row = report["cases"][0]
    assert not row["tool_selection_ok"]
    assert not row["arguments_ok"]
    assert not row["answer_ok"]
    assert report["metrics"]["answer_accuracy"] == 0.0


def test_run_eval_counts_backend_crash_as_failed_case():
    case = {"id": "t2", "category": "no_tool", "question": "q",
            "expected_tools": [], "expected_args": {},
            "answer_rule": {"type": "contains", "value": "ok"}}

    class ExplodingBackend:
        def chat(self, messages, tools=None):
            raise RuntimeError("boom")

    report = run_eval([case], lambda c: ExplodingBackend(), "recording", None)
    row = report["cases"][0]
    assert "backend failure" in row["error"]
    assert not row["answer_ok"]


def test_load_cases_parses_jsonl_and_rejects_empty_file(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps({"id": "a", "question": "q"}) + "\n", encoding="utf-8"
    )
    assert load_cases(path)[0]["id"] == "a"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no cases"):
        load_cases(empty)


# --------------------------------------------------------------------------
# gate
# --------------------------------------------------------------------------

def base_metrics():
    return {
        "tool_selection_accuracy": 0.9,
        "argument_accuracy": 0.8,
        "answer_accuracy": 0.7,
    }


def test_gate_passes_when_metrics_equal_baseline():
    baseline = {"metrics": base_metrics()}
    passed, failures = compare({"metrics": base_metrics()}, baseline)
    assert passed and failures == []


def test_gate_passes_when_metrics_exceed_baseline():
    better = {k: min(1.0, v + 0.05) for k, v in base_metrics().items()}
    passed, _ = compare({"metrics": better}, {"metrics": base_metrics()})
    assert passed


def test_gate_fails_on_any_drop():
    worse = base_metrics()
    worse["answer_accuracy"] = 0.69
    passed, failures = compare({"metrics": worse}, {"metrics": base_metrics()})
    assert not passed
    assert failures == [("answer_accuracy", 0.69, 0.7)]


def test_gate_tolerates_float_noise():
    worse = base_metrics()
    worse["answer_accuracy"] = 0.7 - 1e-12
    passed, _ = compare({"metrics": worse}, {"metrics": base_metrics()})
    assert passed


def test_gate_ignores_latency_and_extra_metrics():
    results = {"metrics": {**base_metrics(), "latency_ms_p50": 99999}}
    passed, _ = compare(results, {"metrics": base_metrics()})
    assert passed


def test_gate_cli_exit_codes(tmp_path, monkeypatch):
    from evals import gate

    results = tmp_path / "r.json"
    baseline = tmp_path / "b.json"
    baseline.write_text(json.dumps({"metrics": base_metrics()}), encoding="utf-8")
    results.write_text(json.dumps({"metrics": base_metrics()}), encoding="utf-8")
    assert gate.main(["--results", str(results), "--baseline", str(baseline)]) == 0

    results.write_text(json.dumps({"metrics": {**base_metrics(), "answer_accuracy": 0.1}}),
                       encoding="utf-8")
    assert gate.main(["--results", str(results), "--baseline", str(baseline)]) == 1

    assert gate.main(
        ["--results", str(tmp_path / "missing.json"), "--baseline", str(baseline)]
    ) == 2
