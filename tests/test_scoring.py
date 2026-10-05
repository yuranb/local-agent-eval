"""Tests for the pure scoring logic in evals/scoring.py."""
import pytest

from agent.loop import AgentResult
from evals.scoring import (
    answer_ok,
    arguments_ok,
    compute_metrics,
    normalize_text,
    percentile,
    score_case,
    tool_selection_ok,
)


def call(tool, **arguments):
    return {"tool": tool, "arguments": arguments, "result": {}}


# --------------------------------------------------------------------------
# tool selection
# --------------------------------------------------------------------------

def test_tool_selection_requires_exact_set_match():
    assert tool_selection_ok(["calculator"], ["calculator"])
    assert tool_selection_ok([], [])
    assert not tool_selection_ok(["calculator"], [])
    assert not tool_selection_ok(["calculator"], ["calculator", "search_docs"])
    assert tool_selection_ok(["a", "b"], ["b", "a"])  # order does not matter


# --------------------------------------------------------------------------
# argument matching
# --------------------------------------------------------------------------

def test_arguments_ok_when_expected_args_are_subset_of_call():
    calls = [call("calculator", expression="12*12")]
    assert arguments_ok({"calculator": {"expression": "12*12"}}, calls)


def test_arguments_ok_ignores_extra_arguments_in_call():
    calls = [call("search_docs", query="fox", top_k=5)]
    assert arguments_ok({"search_docs": {"query": "fox"}}, calls)


def test_arguments_fails_when_tool_not_called():
    assert not arguments_ok({"calculator": {"expression": "1+1"}}, [])


def test_arguments_fails_on_wrong_value():
    calls = [call("calculator", expression="12*13")]
    assert not arguments_ok({"calculator": {"expression": "12*12"}}, calls)


def test_arguments_passes_if_any_call_of_the_tool_matches():
    calls = [call("calculator", expression="5+5"), call("calculator", expression="12*12")]
    assert arguments_ok({"calculator": {"expression": "12*12"}}, calls)


def test_arguments_numbers_compare_across_types():
    calls = [call("add_workdays", date_str="2026-10-05", days="3")]
    assert arguments_ok(
        {"add_workdays": {"date_str": "2026-10-05", "days": 3}}, calls
    )


def test_arguments_whitespace_and_case_insensitive():
    calls = [call("search_docs", query="Four  Score")]
    assert arguments_ok({"search_docs": {"query": "four score"}}, calls)


def test_arguments_ignore_formatting_whitespace_in_expressions():
    # Real model behaviour (qwen2.5:7b): spaces around operators. Formatting
    # is not an argument error; the semantics are identical.
    calls = [call("calculator", expression="744 / 8")]
    assert arguments_ok({"calculator": {"expression": "744/8"}}, calls)


def test_arguments_whitespace_removal_does_not_forgive_reordered_words():
    calls = [call("search_docs", query="Address Gettysburg first words")]
    assert not arguments_ok(
        {"search_docs": {"query": "Gettysburg Address first words"}}, calls
    )


# --------------------------------------------------------------------------
# answer rules
# --------------------------------------------------------------------------

def test_answer_contains_is_case_insensitive():
    assert answer_ok({"type": "contains", "value": "PARIS"}, "The capital is Paris.")
    assert not answer_ok({"type": "contains", "value": "Paris"}, "Berlin")


def test_answer_regex():
    rule = {"type": "regex", "value": r"\bAu\b"}
    assert answer_ok(rule, "The symbol is Au (gold).")
    assert not answer_ok(rule, "gold")


def test_answer_rejects_unknown_rule_type():
    with pytest.raises(ValueError):
        answer_ok({"type": "fuzzy", "value": "x"}, "x")


# --------------------------------------------------------------------------
# percentile
# --------------------------------------------------------------------------

def test_percentile_empty_is_none():
    assert percentile([], 50) is None


def test_percentile_single_value():
    assert percentile([42], 50) == 42
    assert percentile([42], 95) == 42


def test_percentile_p50_of_odd_count_is_middle_value():
    assert percentile([10, 20, 30], 50) == 20


def test_percentile_interpolates_between_neighbours():
    # p50 of [10, 20] is 15 with linear interpolation.
    assert percentile([10, 20], 50) == 15
    assert percentile([10, 20, 30, 40], 95) == pytest.approx(38.5)


# --------------------------------------------------------------------------
# score_case / compute_metrics
# --------------------------------------------------------------------------

def case_fixture(**overrides):
    case = {
        "id": "x-001",
        "category": "calculator",
        "question": "What is 12*12?",
        "expected_tools": ["calculator"],
        "expected_args": {"calculator": {"expression": "12*12"}},
        "answer_rule": {"type": "contains", "value": "144"},
    }
    case.update(overrides)
    return case


def test_score_case_all_pass():
    result = AgentResult(answer="It is 144.", tool_calls=[call("calculator", expression="12*12")])
    row = score_case(case_fixture(), result, latency_ms=7)
    assert row["tool_selection_ok"] and row["arguments_ok"] and row["answer_ok"]
    assert row["arguments_evaluated"] is True
    assert row["latency_ms"] == 7


def test_score_case_no_tool_case_excludes_args_from_denominator():
    case = case_fixture(
        expected_tools=[], expected_args={}, answer_rule={"type": "contains", "value": "hello"}
    )
    row = score_case(case, AgentResult(answer="hello"), latency_ms=1)
    assert row["arguments_evaluated"] is False
    assert not row["arguments_ok"]


def test_score_case_loop_error_fails_answer():
    result = AgentResult(answer="", error="model did not produce a final answer within 5 steps")
    row = score_case(case_fixture(), result, latency_ms=1)
    assert not row["answer_ok"]


def test_compute_metrics_aggregates_and_uses_correct_denominators():
    perfect = dict(tool_selection_ok=True, arguments_ok=True, answer_ok=True, latency_ms=10)
    scored = [
        {**perfect, "id": "a", "category": "calculator", "arguments_evaluated": True},
        {**perfect, "id": "b", "category": "no_tool", "arguments_evaluated": False,
         "arguments_ok": False},
        # case c fails everything
        {**perfect, "id": "c", "category": "calculator", "arguments_evaluated": True,
         "tool_selection_ok": False, "arguments_ok": False, "answer_ok": False},
    ]
    metrics = compute_metrics(scored)
    assert metrics["total_cases"] == 3
    assert metrics["tool_selection_accuracy"] == pytest.approx(2 / 3)
    # argument_accuracy denominator counts only arguments_evaluated cases (a, c)
    assert metrics["argument_accuracy"] == pytest.approx(1 / 2)
    assert metrics["answer_accuracy"] == pytest.approx(2 / 3)
    assert metrics["latency_ms_p50"] == 10
