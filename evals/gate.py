"""Regression gate: fail if accuracy metrics drop below evals/baseline.json.

Only the three accuracy metrics are gated. Latency is reported but never
gated because it is machine-dependent (DECISIONS.md D4). Exit codes:
  0 = all metrics at or above baseline
  1 = at least one metric below baseline
  2 = inputs missing or unreadable
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GATED_METRICS = [
    "tool_selection_accuracy",
    "argument_accuracy",
    "answer_accuracy",
]
TOLERANCE = 1e-9


def compare(results: dict, baseline: dict) -> tuple[bool, list]:
    """Return (passed, list of (metric, actual, required) failures)."""
    failures = []
    actual_metrics = results.get("metrics", {})
    baseline_metrics = baseline.get("metrics", {})
    for metric in GATED_METRICS:
        if metric not in baseline_metrics:
            continue  # baseline predates this metric; nothing to enforce yet
        if metric not in actual_metrics:
            failures.append((metric, None, baseline_metrics[metric]))
            continue
        if actual_metrics[metric] < baseline_metrics[metric] - TOLERANCE:
            failures.append((metric, actual_metrics[metric], baseline_metrics[metric]))
    return not failures, failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        results = json.loads(args.results.read_text(encoding="utf-8"))
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"gate error: cannot read inputs: {exc}")
        return 2

    passed, failures = compare(results, baseline)

    print("metric                       actual    required")
    for metric in GATED_METRICS:
        actual = results.get("metrics", {}).get(metric)
        required = baseline.get("metrics", {}).get(metric)
        actual_s = f"{actual:.3f}" if isinstance(actual, (int, float)) else "missing"
        required_s = f"{required:.3f}" if isinstance(required, (int, float)) else "-"
        print(f"{metric:28s} {actual_s:>7s}   {required_s:>7s}")

    if not passed:
        for metric, actual, required in failures:
            print(
                f"FAIL: {metric} is {actual!r}, baseline requires >= {required!r}",
                file=sys.stderr,
            )
        return 1
    print("gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
