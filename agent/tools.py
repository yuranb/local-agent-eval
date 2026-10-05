"""The three local tools the agent can call. No network access anywhere here.

Each tool is a plain function taking simple JSON-friendly arguments and
returning a JSON-friendly dict, plus the JSON-schema block that is handed to
the model so it knows how to call the tool.
"""
from __future__ import annotations

import ast
import operator
from datetime import date, datetime, timedelta
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


class ToolExecutionError(Exception):
    """Raised when a tool receives bad input; the agent loop turns this into
    an {"error": ...} observation for the model instead of crashing."""


# --------------------------------------------------------------------------
# Tool 1: search_docs
# --------------------------------------------------------------------------

def search_docs(query: str, top_k: int = 3) -> dict:
    """Search the .txt files in docs/ and return matching line snippets.

    Scoring is deliberately simple: split the query into words; a line scores
    one point per query word it contains (case-insensitive). Lines with a
    score of 0 are dropped, the rest are ranked by score and returned.
    """
    if not query or not query.strip():
        raise ToolExecutionError("query must be a non-empty string")
    top_k = int(top_k)
    if top_k < 1:
        raise ToolExecutionError("top_k must be >= 1")

    words = [w.lower() for w in query.split() if w.strip()]
    hits: list[dict] = []
    for path in sorted(DOCS_DIR.glob("*.txt")):
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                text = line.strip()
                low = text.lower()
                score = sum(1 for w in words if w in low)
                if score > 0:
                    hits.append(
                        {"file": path.stem, "line": lineno, "score": score, "text": text}
                    )
    hits.sort(key=lambda h: (-h["score"], h["file"], h["line"]))
    return {"query": query, "snippets": hits[:top_k], "total_matches": len(hits)}


SEARCH_DOCS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_docs",
        "description": (
            "Search the local document collection (public-domain texts in the "
            "docs/ folder) and return the most relevant line snippets. Use it "
            "for any question about what a document says."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Words to look for, e.g. 'four score and seven'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "How many snippets to return (default 3).",
                },
            },
            "required": ["query"],
        },
    },
}


# --------------------------------------------------------------------------
# Tool 2: calculator
# --------------------------------------------------------------------------

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise ToolExecutionError("division by zero")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise ToolExecutionError(f"unsupported expression element: {ast.dump(node)[:80]}")


def calculator(expression: str) -> dict:
    """Evaluate an arithmetic expression using Python's ast module.

    Only numbers and +, -, *, /, //, %, ** and parentheses are accepted;
    anything else (names, calls, attribute access, ...) is rejected before it
    is ever evaluated, so there is no code-execution surface.
    """
    if not expression or not expression.strip():
        raise ToolExecutionError("expression must be a non-empty string")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolExecutionError(f"invalid expression: {exc.msg}") from exc
    value = _eval_node(tree)
    # Whole-number results are returned as int so "12*12" yields 144 not 144.0.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return {"expression": expression, "value": value}


CALCULATOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": (
            "Evaluate an arithmetic expression. Supports +, -, *, /, //, %, "
            "** and parentheses. Use it for any math instead of guessing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The expression to evaluate, e.g. '(3+4)*12'",
                },
            },
            "required": ["expression"],
        },
    },
}


# --------------------------------------------------------------------------
# Tool 3: add_workdays
# --------------------------------------------------------------------------

def add_workdays(date_str: str, days: int) -> dict:
    """Add N working days (Mon-Fri) to a date; Saturday and Sunday are skipped.

    days may be 0 or negative (going backwards). Accepts ISO dates
    (YYYY-MM-DD) or 'YYYY-MM-DD HH:MM' timestamps; the answer is always an
    ISO date.
    """
    try:
        start = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError) as exc:
        raise ToolExecutionError(
            "date must be in YYYY-MM-DD format"
        ) from exc
    try:
        days = int(days)
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError("days must be an integer") from exc

    step = 1 if days >= 0 else -1
    remaining = abs(days)
    current = start
    while remaining > 0:
        current += timedelta(days=step)
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            remaining -= 1

    return {
        "start_date": start.isoformat(),
        "days": days,
        "result_date": current.isoformat(),
        "result_weekday": current.strftime("%A"),
    }


ADD_WORKDAYS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "add_workdays",
        "description": (
            "Add N working days (Monday-Friday) to a date; weekends are "
            "skipped. Days can be 0 or negative."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of working days to add",
                },
            },
            "required": ["date_str", "days"],
        },
    },
}


# --------------------------------------------------------------------------
# Dispatch table used by the agent loop
# --------------------------------------------------------------------------

TOOLS: dict[str, callable] = {
    "search_docs": search_docs,
    "calculator": calculator,
    "add_workdays": add_workdays,
}

TOOL_SCHEMAS: list[dict] = [
    SEARCH_DOCS_SCHEMA,
    CALCULATOR_SCHEMA,
    ADD_WORKDAYS_SCHEMA,
]


def execute_tool(name: str, arguments: dict) -> dict:
    """Run a tool by name. Unknown tools and bad arguments both become
    {"error": ...} dicts so the model can see what went wrong."""
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    if not isinstance(arguments, dict):
        return {"error": f"arguments for {name} must be an object"}
    try:
        return fn(**arguments)
    except ToolExecutionError as exc:
        return {"error": str(exc)}
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
