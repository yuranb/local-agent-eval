"""Pure scoring functions for the eval (scope item 5).

Everything here is deterministic and model-free so it is fully unit-testable.
The eval runner just feeds case + AgentResult pairs into `score_case`.
"""
from __future__ import annotations

import re


def normalize_text(value: str) -> str:
    return " ".join(str(value).split()).strip().lower()


def _canonical(value) -> str:
    """Canonical form of an argument value for comparison.

    Numbers compare numerically ("3" == 3). Text ignores case and ALL
    whitespace, so an expression like "744 / 8" matches "744/8" — formatting
    differences are not argument errors. Word choice and order still matter,
    so paraphrased search queries still fail.
    """
    if isinstance(value, bool):
        return normalize_text(value).replace(" ", "")
    if isinstance(value, (int, float)):
        return repr(float(value))
    text = normalize_text(value).replace(" ", "")
    try:
        return repr(float(text))
    except ValueError:
        return text


def tool_selection_ok(expected_tools: list, used_tools: list) -> bool:
    """The set of tools the agent called must equal the expected set."""
    return sorted(expected_tools) == sorted(used_tools)


def arguments_ok(expected_args: dict, tool_calls: list) -> bool:
    """Every expected (tool -> args) must appear in some actual call of that
    tool, with the expected args being a subset of the call's arguments."""
    for tool, expected in expected_args.items():
        calls = [c for c in tool_calls if c["tool"] == tool]
        if not calls:
            return False
        satisfied = any(
            all(
                _canonical(want) == _canonical(call["arguments"].get(key))
                for key, want in expected.items()
            )
            for call in calls
        )
        if not satisfied:
            return False
    return True


def answer_ok(rule: dict, answer: str) -> bool:
    rule_type = rule.get("type")
    value = rule.get("value", "")
    if rule_type == "contains":
        return normalize_text(value) in normalize_text(answer)
    if rule_type == "regex":
        return re.search(value, answer) is not None
    raise ValueError(f"unknown answer rule type: {rule_type!r}")


def percentile(values: list, p: float):
    """P-statistic with linear interpolation (same convention as numpy's
    default). Returns None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def score_case(case: dict, result, latency_ms: int) -> dict:
    """Turn one (case, AgentResult) pair into a flat scoring record."""
    used = result.tools_used()
    tool_ok = tool_selection_ok(case["expected_tools"], used)
    needs_args = bool(case["expected_args"])
    args_ok = arguments_ok(case["expected_args"], result.tool_calls) if needs_args else False
    try:
        final_ok = answer_ok(case["answer_rule"], result.answer) and result.error is None
    except ValueError:
        final_ok = False

    return {
        "id": case["id"],
        "category": case["category"],
        "tool_selection_ok": tool_ok,
        "arguments_evaluated": needs_args,
        "arguments_ok": args_ok,
        "answer_ok": final_ok,
        "used_tools": used,
        "answer": result.answer,
        "error": result.error,
        "latency_ms": latency_ms,
    }


def compute_metrics(scored_cases: list) -> dict:
    total = len(scored_cases)
    args_cases = [c for c in scored_cases if c["arguments_evaluated"]]
    latencies = [c["latency_ms"] for c in scored_cases]
    return {
        "total_cases": total,
        "tool_selection_accuracy": (
            sum(1 for c in scored_cases if c["tool_selection_ok"]) / total if total else 0.0
        ),
        "argument_accuracy": (
            sum(1 for c in args_cases if c["arguments_ok"]) / len(args_cases)
            if args_cases
            else 0.0
        ),
        "answer_accuracy": (
            sum(1 for c in scored_cases if c["answer_ok"]) / total if total else 0.0
        ),
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
    }
