"""Validate evals/cases.jsonl structurally AND for internal consistency.

The consistency half is the interesting part: every search/calculator/workday
case's answer rule is checked against the *real* tool output for its expected
arguments, so the dataset can never silently drift away from the tools.
"""
import json
import re
from pathlib import Path

import pytest

from agent.tools import add_workdays, calculator, search_docs

CASES_PATH = Path(__file__).resolve().parent.parent / "evals" / "cases.jsonl"

VALID_TOOLS = {"search_docs", "calculator", "add_workdays"}


def load_cases():
    cases = []
    with CASES_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


CASES = load_cases()


def test_dataset_has_exactly_50_cases():
    assert len(CASES) == 50


def test_dataset_case_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_dataset_has_at_least_10_no_tool_cases():
    no_tool = [c for c in CASES if c["expected_tools"] == []]
    assert len(no_tool) >= 10


def test_every_case_has_required_fields():
    required = {"id", "category", "question", "expected_tools", "expected_args", "answer_rule"}
    for case in CASES:
        missing = required - case.keys()
        assert not missing, f"{case.get('id')} is missing {missing}"
        assert case["question"].strip(), f"{case['id']} has an empty question"


def test_expected_tools_are_known_and_args_reference_them():
    for case in CASES:
        for tool in case["expected_tools"]:
            assert tool in VALID_TOOLS, f"{case['id']}: unknown tool {tool}"
        for tool in case["expected_args"]:
            assert tool in case["expected_tools"], (
                f"{case['id']}: expected_args mentions {tool} which is not in "
                "expected_tools"
            )


def test_answer_rules_are_wellformed():
    for case in CASES:
        rule = case["answer_rule"]
        assert rule["type"] in {"contains", "regex"}, f"{case['id']}: bad rule type"
        assert rule["value"], f"{case['id']}: empty rule value"
        if rule["type"] == "regex":
            re.compile(rule["value"])  # raises if the pattern is broken


def test_expected_args_match_tool_signatures():
    for case in CASES:
        for tool, args in case["expected_args"].items():
            if not args:
                continue
            try:
                if tool == "search_docs":
                    search_docs(args["query"])
                elif tool == "calculator":
                    calculator(args["expression"])
                elif tool == "add_workdays":
                    add_workdays(args["date_str"], args["days"])
            except Exception as exc:  # noqa: BLE001 - report which case broke
                pytest.fail(f"{case['id']}: expected args do not run: {exc}")


def _rule_matches(rule, text):
    if rule["type"] == "contains":
        return rule["value"].lower() in text.lower()
    return re.search(rule["value"], text) is not None


def test_search_case_rules_match_real_snippets():
    for case in CASES:
        if case["category"] != "search_docs":
            continue
        query = case["expected_args"]["search_docs"]["query"]
        result = search_docs(query, top_k=5)
        assert result["total_matches"] > 0, f"{case['id']}: expected query finds nothing"
        text = " ".join(s["text"] for s in result["snippets"])
        assert _rule_matches(case["answer_rule"], text), (
            f"{case['id']}: answer rule never matches the real search output"
        )


def test_calculator_case_rules_match_real_tool_output():
    for case in CASES:
        if case["category"] != "calculator":
            continue
        expression = case["expected_args"]["calculator"]["expression"]
        value = calculator(expression)["value"]
        assert _rule_matches(case["answer_rule"], str(value)), (
            f"{case['id']}: rule {case['answer_rule']} does not match "
            f"calculator output {value}"
        )


def test_workday_case_rules_match_real_tool_output():
    for case in CASES:
        if case["category"] != "add_workdays":
            continue
        args = case["expected_args"]["add_workdays"]
        result = add_workdays(args["date_str"], args["days"])
        text = f"{result['result_date']} {result['result_weekday']}"
        assert _rule_matches(case["answer_rule"], text), (
            f"{case['id']}: rule does not match add_workdays output {text}"
        )
