"""Exact rational-number arithmetic for the ``--fraction`` subcommand.

This module evaluates a narrow subset of the calculator's expression syntax
using ``fractions.Fraction`` for exact rational results.  It deliberately does
**not** use ``decimal.Decimal`` approximations and does not support built-in
functions (``sqrt``, ``ln``, ``sin``, etc.) or non-integer exponents.

Supported syntax:
  * binary operators ``+ - * /`` and parentheses
  * unary ``+`` and ``-``
  * ``^`` for exponentiation, but **only with integer exponents**

Deliberately out of scope (kept in this module, not in the parser core):
  * REPL ``ans`` integration
  * mixing with ``--convert``, ``--compound-interest``, or ``--convert-unit``
  * built-in mathematical functions
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from fractions import Fraction

from .parser import (
    CalcError,
    DivisionByZeroError,
    MalformedExpressionError,
    ResultTooLargeError,
    _MAX_DECIMAL_DIGITS,
    _MAX_DEPTH,
    _MAX_EXPONENT,
    _MAX_EXPRESSION_LENGTH,
    _MAX_RESULT_BITS,
    _check_paren_depth,
    _tokenize,
)


def _guard_fraction(value: Fraction) -> Fraction:
    """Reject intermediate Fractions whose numerator or denominator is too large.

    ``Fraction`` automatically cancels common factors, so a single operation
    rarely produces runaway integers.  However, a long chain of additions with
    pairwise-coprime denominators (e.g. ``1/2 + 1/3 + 1/5 + ...``) grows the
    common denominator as a product.  Checking after every operation prevents
    that chain from exhausting memory or CPU.
    """
    if not isinstance(value, Fraction):
        # This should never happen, but keep the failure inside CalcError.
        raise MalformedExpressionError("invalid fraction result")

    # ``Fraction`` keeps the denominator positive and the sign on the numerator.
    # When the numerator or denominator exceeds Python's own integer-to-string
    # limit, ``str()`` raises ``ValueError``; treat that the same as "too large".
    try:
        num_digits = len(str(abs(value.numerator)))
        den_digits = len(str(abs(value.denominator)))
    except ValueError as exc:
        raise ResultTooLargeError("result too large to print") from exc
    if num_digits > _MAX_DECIMAL_DIGITS or den_digits > _MAX_DECIMAL_DIGITS:
        raise ResultTooLargeError("result too large to print")
    return value


def _parse_number(text: str) -> Fraction:
    """Convert a NUMBER token to an exact ``Fraction``.

    Decimal literals are converted through ``Decimal`` first to avoid the
    binary-float artifacts that ``Fraction(0.1)`` would introduce.
    """
    try:
        if "e" in text or "E" in text or "." in text:
            decimal_value = Decimal(text)
            # Guard against pathological exponents before Fraction() tries to
            # expand the Decimal into full numerator/denominator integers.
            if abs(decimal_value.adjusted()) > _MAX_RESULT_BITS:
                raise ResultTooLargeError("numeric literal too large")
            number = Fraction(decimal_value)
        else:
            # Avoid allocating a huge int just to reject it.
            if len(text) > _MAX_DECIMAL_DIGITS:
                raise ResultTooLargeError("numeric literal too large")
            number = Fraction(int(text), 1)
    except (ValueError, OverflowError) as exc:
        raise ResultTooLargeError("numeric literal too large") from exc
    return _guard_fraction(number)


def _check_fraction_exponent(exponent: Fraction) -> int:
    """Validate that ``exponent`` is an integer within the safe size bound."""
    if exponent.denominator != 1:
        raise MalformedExpressionError("non-integer exponent is not supported")
    exp_int = exponent.numerator
    if abs(exp_int) > _MAX_EXPONENT:
        raise ResultTooLargeError("exponent too large")
    return exp_int


def _fraction_power(base: Fraction, exponent: Fraction) -> Fraction:
    """Compute ``base ^ exponent`` for integer exponents only."""
    exp_int = _check_fraction_exponent(exponent)

    if base == 0 and exp_int < 0:
        raise DivisionByZeroError("division by zero")

    try:
        result = base ** exp_int
    except ZeroDivisionError as exc:
        raise DivisionByZeroError("division by zero") from exc

    return _guard_fraction(result)


class _FractionParser:
    """Recursive-descent parser that evaluates to ``fractions.Fraction``."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.depth = 0
        if not self.tokens:
            raise MalformedExpressionError("empty expression")

    def _peek(self) -> tuple[str, str] | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _consume(self, expected_type: str | None = None) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise MalformedExpressionError("unexpected end of expression")
        if expected_type is not None and token[0] != expected_type:
            raise MalformedExpressionError(
                f"expected {expected_type}, got {token[1]!r}"
            )
        self.pos += 1
        return token

    def parse(self) -> Fraction:
        result = self._expr()
        if self.pos != len(self.tokens):
            remaining = self._peek()
            raise MalformedExpressionError(f"unexpected token: {remaining[1]!r}")
        return result

    @contextmanager
    def _nested(self):
        """Track recursion depth to avoid RecursionError on abusive input."""
        self.depth += 1
        if self.depth > _MAX_DEPTH:
            raise MalformedExpressionError("expression too deeply nested")
        try:
            yield
        finally:
            self.depth -= 1

    def _expr(self) -> Fraction:
        result = self._term()
        while True:
            token = self._peek()
            if token is None:
                break
            if token[0] == "PLUS":
                self._consume("PLUS")
                rhs = self._term()
                result = _guard_fraction(result + rhs)
            elif token[0] == "MINUS":
                self._consume("MINUS")
                rhs = self._term()
                result = _guard_fraction(result - rhs)
            else:
                break
        return result

    def _term(self) -> Fraction:
        result = self._unary()
        while True:
            token = self._peek()
            if token is None:
                break
            if token[0] == "MUL":
                self._consume("MUL")
                rhs = self._unary()
                result = _guard_fraction(result * rhs)
            elif token[0] == "DIV":
                self._consume("DIV")
                divisor = self._unary()
                if divisor == 0:
                    raise DivisionByZeroError("division by zero")
                result = _guard_fraction(result / divisor)
            else:
                break
        return result

    def _unary(self) -> Fraction:
        token = self._peek()
        if token is not None and token[0] == "PLUS":
            self._consume("PLUS")
            with self._nested():
                return _guard_fraction(+self._unary())
        if token is not None and token[0] == "MINUS":
            self._consume("MINUS")
            with self._nested():
                return _guard_fraction(-self._unary())
        return self._power()

    def _power(self) -> Fraction:
        base = self._primary()
        token = self._peek()
        if token is not None and token[0] == "POW":
            self._consume("POW")
            with self._nested():
                exponent = self._unary()
            return _fraction_power(base, exponent)
        return base

    def _primary(self) -> Fraction:
        token = self._peek()
        if token is None:
            raise MalformedExpressionError("unexpected end of expression")
        if token[0] == "NUMBER":
            self._consume("NUMBER")
            return _parse_number(token[1])
        if token[0] == "IDENT":
            self._consume("IDENT")
            raise MalformedExpressionError(
                "functions are not supported in fraction mode"
            )
        if token[0] == "LPAREN":
            self._consume("LPAREN")
            with self._nested():
                result = self._expr()
            self._consume("RPAREN")
            return result
        raise MalformedExpressionError(f"unexpected token: {token[1]!r}")


def calculate_fraction(expression: str) -> Fraction:
    """Evaluate an expression using exact rational arithmetic.

    Supported operators: ``+``, ``-``, ``*``, ``/``, ``^``, and parentheses.
    ``^`` accepts integer exponents only (including negative integers).  Decimal
    literals such as ``0.5`` are converted exactly, not via binary ``float``.

    Args:
        expression: The rational expression to evaluate.

    Returns:
        A fully-reduced ``fractions.Fraction``.

    Raises:
        MalformedExpressionError: If the expression is invalid, too long, or
            uses unsupported syntax (functions or non-integer exponents).
        DivisionByZeroError: If a division by zero occurs.
        ResultTooLargeError: If a result would be unreasonably large or
            impossible to print.
    """
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise MalformedExpressionError("expression too long")
    tokens = list(_tokenize(expression))
    _check_paren_depth(tokens)
    return _guard_fraction(_FractionParser(tokens).parse())


def format_fraction(value: Fraction) -> str:
    """Return a concise string representation of a ``Fraction``.

    Integers are printed without a ``/1`` denominator; fractions use the
    canonical ``numerator/denominator`` form with the sign on the numerator.
    """
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"
