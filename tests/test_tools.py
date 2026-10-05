"""Unit tests for the three tools in agent/tools.py. No model involved."""
import pytest

from agent.tools import (
    ToolExecutionError,
    add_workdays,
    calculator,
    execute_tool,
    search_docs,
    TOOL_SCHEMAS,
)


# --------------------------------------------------------------------------
# search_docs
# --------------------------------------------------------------------------

def test_search_docs_finds_gettysburg_phrase():
    result = search_docs("four score and seven years ago")
    assert result["total_matches"] >= 1
    assert result["snippets"][0]["file"] == "gettysburg_address"
    assert "Four score and seven" in result["snippets"][0]["text"]


def test_search_docs_matches_are_scored_by_word_count():
    # The opening line of art_of_war contains five of the query words, while
    # lines in other files contain at most one or two of them.
    result = search_docs("art of war vital importance")
    top = result["snippets"][0]
    assert top["file"] == "art_of_war"
    assert top["score"] == 5
    assert all(s["score"] <= top["score"] for s in result["snippets"])


def test_search_docs_no_match_returns_empty_snippets():
    result = search_docs("xylophone quartermaster")
    assert result["snippets"] == []
    assert result["total_matches"] == 0


def test_search_docs_case_insensitive():
    result = search_docs("SHALL I COMPARE THEE")
    assert any(s["file"] == "sonnet_18" for s in result["snippets"])


def test_search_docs_top_k_limits_results():
    result = search_docs("the", top_k=2)
    assert len(result["snippets"]) <= 2


def test_search_docs_rejects_empty_query():
    with pytest.raises(ToolExecutionError):
        search_docs("   ")


def test_search_docs_only_indexes_txt_files():
    # SOURCES.md lives in docs/ too but must never show up in results.
    result = search_docs("public domain license source")
    assert all(s["file"] != "SOURCES" for s in result["snippets"])


# --------------------------------------------------------------------------
# calculator
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2+2", 4),
        ("12*12", 144),
        ("(3+4)*12", 84),
        ("10/4", 2.5),
        ("2**10", 1024),
        ("100-25", 75),
        ("7//2", 3),
        ("9%4", 1),
        ("-5+3", -2),
        ("3.5*2", 7),  # whole-number float is normalized to int
    ],
)
def test_calculator_basic_expressions(expression, expected):
    assert calculator(expression)["value"] == expected


def test_calculator_reports_division_by_zero_as_tool_error():
    with pytest.raises(ToolExecutionError):
        calculator("1/0")


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "open('/etc/passwd').read()",
        "(lambda: 42)()",
        "x",
        "1 +",
        "",
        "   ",
    ],
)
def test_calculator_rejects_non_arithmetic_input(expression):
    with pytest.raises(ToolExecutionError):
        calculator(expression)


# --------------------------------------------------------------------------
# add_workdays
# --------------------------------------------------------------------------

def test_add_workdays_within_same_week():
    # 2026-10-05 is a Monday; +3 workdays -> Thursday.
    result = add_workdays("2026-10-05", 3)
    assert result["result_date"] == "2026-10-08"
    assert result["result_weekday"] == "Thursday"


def test_add_workdays_crosses_weekend():
    # Friday 2026-10-09 + 1 workday -> Monday 2026-10-12.
    result = add_workdays("2026-10-09", 1)
    assert result["result_date"] == "2026-10-12"
    assert result["result_weekday"] == "Monday"


def test_add_workdays_multiple_weeks():
    # Monday 2026-10-05 + 10 workdays = two full weeks -> Monday 2026-10-19.
    assert add_workdays("2026-10-05", 10)["result_date"] == "2026-10-19"


def test_add_workdays_zero_days_returns_start():
    result = add_workdays("2026-10-10", 0)  # a Saturday
    assert result["result_date"] == "2026-10-10"


def test_add_workdays_negative_days_go_backwards():
    # Monday 2026-10-12 - 1 workday -> Friday 2026-10-09.
    result = add_workdays("2026-10-12", -1)
    assert result["result_date"] == "2026-10-09"
    assert result["result_weekday"] == "Friday"


def test_add_workdays_starting_on_weekend():
    # Saturday 2026-10-10 + 1 workday -> Monday 2026-10-12.
    assert add_workdays("2026-10-10", 1)["result_date"] == "2026-10-12"


def test_add_workdays_rejects_bad_date_format():
    with pytest.raises(ToolExecutionError):
        add_workdays("10/05/2026", 1)


def test_add_workdays_rejects_non_integer_days():
    with pytest.raises(ToolExecutionError):
        add_workdays("2026-10-05", "lots")


# --------------------------------------------------------------------------
# execute_tool dispatch
# --------------------------------------------------------------------------

def test_execute_tool_unknown_tool_returns_error_dict():
    out = execute_tool("send_email", {"to": "x"})
    assert out == {"error": "unknown tool: send_email"}


def test_execute_tool_bad_arguments_become_error_dict():
    out = execute_tool("calculator", {"expr": "1+1"})  # wrong kwarg name
    assert "error" in out


def test_execute_tool_success_path():
    out = execute_tool("calculator", {"expression": "2*21"})
    assert out == {"expression": "2*21", "value": 42}


def test_tool_schemas_are_wellformed_and_match_dispatch():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert names == {"search_docs", "calculator", "add_workdays"}
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert isinstance(params.get("properties"), dict)
