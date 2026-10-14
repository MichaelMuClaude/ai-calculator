"""Date calculation mode for the ``--date`` subcommand.

Supports simple day-level date arithmetic:
  * ``today`` resolves to the current local date.
  * ``YYYY-MM-DD`` literal dates.
  * ``date + days`` and ``date - days`` -> resulting date (YYYY-MM-DD).
  * ``date - date`` -> signed day difference.

Months and years are intentionally out of scope because their lengths are
ambiguous (e.g. "Jan 31 + 1 month" has no single correct answer).
"""

from __future__ import annotations

import datetime
import re

from .parser import (
    CalcError,
    MalformedExpressionError,
    ResultTooLargeError,
    _MAX_EXPRESSION_LENGTH,
)


class DateCalcError(CalcError):
    """Raised when a date expression or literal is invalid."""


# Strict ``YYYY-MM-DD`` literal (components are range-checked separately).
_DATE_LITERAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A single bare date without an operator is syntactically incomplete.
_SINGLE_DATE_RE = re.compile(r"^\s*(today|\d{4}-\d{2}-\d{2})\s*$")

# One binary operation: date <op> (date | signed day offset).
_DATE_EXPR_RE = re.compile(
    r"^\s*(today|\d{4}-\d{2}-\d{2})\s*"  # left date
    r"(\+|-)\s*"  # operator
    r"(today|\d{4}-\d{2}-\d{2}|[+-]?\d+)\s*$"  # right operand
)


def _today() -> datetime.date:
    """Return the current date.

    This function exists so tests can monkeypatch the "today" value and get
    deterministic results.
    """
    return datetime.date.today()


def _is_date_literal(value: str) -> bool:
    return value == "today" or _DATE_LITERAL_RE.match(value) is not None


def _parse_date(value: str) -> datetime.date:
    """Parse ``today`` or a ``YYYY-MM-DD`` literal into a ``datetime.date``."""
    if value == "today":
        return _today()
    if not _DATE_LITERAL_RE.match(value):
        raise DateCalcError(f"invalid date: {value!r}")
    try:
        year, month, day = map(int, value.split("-"))
        return datetime.date(year, month, day)
    except ValueError as exc:
        raise DateCalcError(f"invalid date: {value!r}") from exc


def _parse_days(value: str) -> int:
    """Parse a day offset integer (with optional leading sign)."""
    try:
        return int(value)
    except ValueError as exc:
        # This path is defensive: the expression regex only permits [+-]?\d+.
        raise DateCalcError(f"invalid day offset: {value!r}") from exc


def _format_date(value: datetime.date) -> str:
    return value.isoformat()


def _format_days(delta: int) -> str:
    return f"{delta} 天"


def calculate_date(expression: str) -> str:
    """Evaluate a date expression and return a human-readable result.

    Returns:
        An ISO date string (``YYYY-MM-DD``) for ``date +/- days`` operations,
        or a signed day count followed by `` 天`` for ``date - date``.

    Raises:
        MalformedExpressionError: If the expression is empty, too long, or
            syntactically invalid.
        DateCalcError: If a date literal is invalid.
        ResultTooLargeError: If an arithmetic operation overflows the supported
            date range.
    """
    if not expression:
        raise MalformedExpressionError("empty expression")

    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise MalformedExpressionError("expression too long")

    if _SINGLE_DATE_RE.match(expression):
        raise MalformedExpressionError(
            "incomplete date expression: expected an operator"
        )

    match = _DATE_EXPR_RE.match(expression)
    if not match:
        raise MalformedExpressionError("invalid date expression")

    left_str, op, right_str = match.group(1), match.group(2), match.group(3)
    left_date = _parse_date(left_str)

    # ``date - date`` -> signed day difference.
    if op == "-" and _is_date_literal(right_str):
        right_date = _parse_date(right_str)
        try:
            delta = (left_date - right_date).days
        except OverflowError as exc:
            raise ResultTooLargeError("date result out of range") from exc
        return _format_days(delta)

    # ``date + date`` is not a meaningful operation.
    if op == "+" and _is_date_literal(right_str):
        raise MalformedExpressionError("adding two dates is not supported")

    # ``date + days`` or ``date - days`` -> resulting date.
    days = _parse_days(right_str)
    try:
        if op == "+":
            result = left_date + datetime.timedelta(days=days)
        else:
            result = left_date - datetime.timedelta(days=days)
    except OverflowError as exc:
        raise ResultTooLargeError("date result out of range") from exc

    return _format_date(result)
