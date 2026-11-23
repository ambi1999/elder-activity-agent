"""Tools the agent can call.

Each tool is a plain Python function with type hints and a docstring.
The Gemini SDK reads these to tell the model what each tool does.
"""

import ast
import logging
import operator
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Only these operations are allowed in the calculator. Anything else
# (function calls, names, attribute access) is rejected, so users can't
# run arbitrary code the way they could with Python's eval().
log = logging.getLogger(__name__)

_OPS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
MAX_EXPONENT = 100
MAX_EXPRESSION_LENGTH = 200


def get_current_time(timezone: str = "UTC") -> str:
    """Get the current date and time.

    Args:
        timezone: An IANA timezone name, e.g. 'UTC', 'Europe/London', 'America/New_York'.
    """
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return f"Error: unknown timezone '{timezone}'. Use an IANA name like 'Europe/London'."
    return datetime.now(tz).strftime("%A %d %B %Y, %H:%M:%S %Z")


# Tool errors go back to the model and appear in /chat's response, so they are
# fixed messages: never the text of a caught exception, which could reveal
# internals (CodeQL py/stack-trace-exposure, CWE-209). Details go to the log.
EXPONENT_TOO_LARGE = f"Error: exponent too large (at most {MAX_EXPONENT})"
NOT_ALLOWED = "Error: only numbers and + - * / // % ** ( ) are allowed"


class _ExponentTooLarge(ValueError):
    """An exponent above MAX_EXPONENT, which could take too long to compute."""


def _evaluate(node: ast.AST) -> float:
    """Evaluate a parsed expression, allowing only numbers and the operators in _OPS."""
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise _ExponentTooLarge
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_evaluate(node.operand))
    raise ValueError("only numbers and + - * / // % ** ( ) are allowed")


def calculate(expression: str) -> str:
    """Evaluate an arithmetic expression and return the result.

    Args:
        expression: The arithmetic to evaluate, e.g. '17 * 23' or '(2 + 3) ** 2'.
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        return "Error: expression too long"
    try:
        result = _evaluate(ast.parse(expression, mode="eval"))
    except ZeroDivisionError:
        return "Error: division by zero"
    except _ExponentTooLarge:
        return EXPONENT_TOO_LARGE
    except (ValueError, SyntaxError, TypeError, OverflowError):
        return NOT_ALLOWED
    return str(result)


def days_until(target_date: str) -> str:
    """Count how many days from today until a given date.

    Args:
        target_date: The date in YYYY-MM-DD format, e.g. '2026-12-25'.
    """
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return f"Error: '{target_date}' is not a valid date. Use YYYY-MM-DD."
    days = (target - date.today()).days
    if days > 0:
        return f"{days} days until {target_date}"
    if days == 0:
        return f"{target_date} is today"
    return f"{target_date} was {-days} days ago"


TOOLS: dict[str, Callable[..., str]] = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "days_until": days_until,
}


def run_tool(name: str, args: dict[str, Any]) -> str:
    """Run a tool by name. Errors are returned as text so the model can recover."""
    func = TOOLS.get(name)
    if func is None:
        return f"Error: unknown tool '{name}'"
    try:
        return func(**args)
    except TypeError:
        log.warning("Tool %s called with bad arguments %s", name, sorted(args))
        return f"Error: bad arguments for {name}; check the tool's parameters"
