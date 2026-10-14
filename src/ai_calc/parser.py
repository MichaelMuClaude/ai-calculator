"""Safe arithmetic expression parser.

Implements a tiny recursive-descent parser for basic arithmetic. It does
not use ``eval``/``exec`` or any other dynamic execution of untrusted input.

Non-integer values are represented as ``decimal.Decimal`` (fixed-precision
decimal floating-point) rather than binary ``float``.  This avoids classic
binary artifacts such as ``0.1 + 0.2 == 0.30000000000000004``.  Division and
non-integer powers are computed with the precision configured by
``decimal.getcontext().prec`` (28 significant digits by default).  This is a
practical fixed precision, not a claim of infinite exactness.
"""

from __future__ import annotations

import math
import re
import sys
from contextlib import contextmanager
from decimal import (
    Decimal,
    DivisionByZero as DecimalDivisionByZero,
    InvalidOperation as DecimalInvalidOperation,
    Overflow as DecimalOverflow,
    getcontext,
)

# Use Decimal's default 28 significant digits for all inexact operations.
getcontext().prec = 28


class CalcError(Exception):
    """Base exception for all calculator errors."""


class MalformedExpressionError(CalcError):
    """Raised when the expression cannot be parsed."""


class DivisionByZeroError(CalcError):
    """Raised when an expression attempts to divide by zero."""


class ResultTooLargeError(CalcError):
    """Raised when a numeric result would be too large to handle safely."""


class NonRealResultError(CalcError):
    """Raised when an operation would yield a non-real (e.g. complex) result."""


# Safety limits for untrusted input.
# Each parenthesis level currently consumes several Python stack frames, so
# this must stay well below the default recursion limit (1000).
_MAX_DEPTH = 150  # parenthesis / recursion nesting
_MAX_EXPONENT = 1_000_000  # absolute value of any integer exponent
_MAX_RESULT_BITS = 1_000_000  # estimated bit length of any integer power
_MAX_EXPRESSION_LENGTH = 10_000  # characters; this is a calculator, not a compiler

_LOG10_2 = math.log10(2)
# Python 3.11+ limits how many digits an int may have when converted to str.
_PYTHON_STR_DIGIT_LIMIT = getattr(sys, "get_int_max_str_digits", lambda: 4300)()
_MAX_DECIMAL_DIGITS = (
    _PYTHON_STR_DIGIT_LIMIT if _PYTHON_STR_DIGIT_LIMIT > 0 else _MAX_RESULT_BITS
)

_TOKEN_SPEC = [
    # HEX must come before NUMBER, otherwise "0x10" is tokenized as
    # NUMBER("0") + IDENT("x10").
    ("HEX", r"0[xX][0-9a-fA-F]+"),
    ("NUMBER", r"\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?"),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("MUL", r"\*"),
    ("DIV", r"/"),
    ("POW", r"\^"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("IDENT", r"[A-Za-z][A-Za-z0-9]*"),
    ("SKIP", r"[ \t]+"),
    ("MISMATCH", r"."),
]

# Built-in mathematical functions callable as FUNCNAME(expression).
# sqrt/ln/log10 stay in Decimal precision; sin/cos/tan fall back to float.
_KNOWN_FUNCTIONS = frozenset({"sqrt", "ln", "log10", "sin", "cos", "tan"})

# Mathematical constants recognized as bare identifiers (lowercase only).
_CONSTANTS = {
    "e": Decimal("2.718281828459045235360287471"),
    "pi": Decimal("3.141592653589793238462643383"),
}
_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC)
)


def _tokenize(text: str):
    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup
        value = match.group()
        if kind == "SKIP":
            continue
        if kind == "MISMATCH":
            raise MalformedExpressionError(f"unexpected character: {value!r}")
        yield (kind, value)


def _check_paren_depth(tokens) -> None:
    """Pre-scan tokens to avoid RecursionError from deeply nested parentheses."""
    depth = 0
    for kind, _ in tokens:
        if kind == "LPAREN":
            depth += 1
            if depth > _MAX_DEPTH:
                raise MalformedExpressionError("expression too deeply nested")
        elif kind == "RPAREN":
            depth -= 1
            if depth < 0:
                raise MalformedExpressionError("unmatched closing parenthesis")
    if depth != 0:
        raise MalformedExpressionError("unmatched opening parenthesis")


def _apply_function(name: str, value):
    """Apply a built-in mathematical function to a fully-evaluated argument.

    sqrt, ln, and log10 use ``decimal.Decimal`` natively and keep full Decimal
    precision.  sin, cos, and tan fall back to Python's ``math`` module (float
    precision); inputs are interpreted as radians.  All domain errors and
    overflow conditions are converted to ``CalcError`` subclasses.
    """
    value = _guard_value(value)
    try:
        if name == "sqrt":
            if value < 0:
                raise NonRealResultError("sqrt of negative number")
            return _guard_value(Decimal(value).sqrt())
        if name == "ln":
            if value <= 0:
                raise NonRealResultError("ln of non-positive number")
            return _guard_value(Decimal(value).ln())
        if name == "log10":
            if value <= 0:
                raise NonRealResultError("log10 of non-positive number")
            d = Decimal(value)
            return _guard_value(d.ln() / Decimal(10).ln())
        # Trigonometric functions use float precision by design.
        if name in ("sin", "cos", "tan"):
            try:
                fv = float(value)
            except OverflowError as exc:
                raise ResultTooLargeError("numeric argument too large") from exc
            if not math.isfinite(fv):
                raise ResultTooLargeError("numeric argument too large")
            func = getattr(math, name)
            try:
                result = func(fv)
            except OverflowError as exc:
                raise ResultTooLargeError("numeric result too large") from exc
            except ValueError as exc:
                raise NonRealResultError("trigonometric argument out of range") from exc
            return _guard_value(_decimal_from_float(result))
    except (DecimalOverflow, DecimalInvalidOperation) as exc:
        raise ResultTooLargeError("numeric result too large") from exc
    # Should never be reached because callers validate the name first.
    raise MalformedExpressionError(f"unknown function: {name}")


def _check_power_size(base, exponent) -> None:
    """Reject power operations that would allocate or print an unreasonably large result."""
    if isinstance(exponent, Decimal):
        if not exponent.is_finite():
            raise ResultTooLargeError("exponent too large")
        # Integral Decimal exponents are subject to the same checks as ints.
        if exponent == exponent.to_integral_value():
            exponent = int(exponent)
        else:
            # Non-integral exponents stay in Decimal; bound their size.
            if abs(exponent) > _MAX_EXPONENT:
                raise ResultTooLargeError("exponent too large")
            return

    if not isinstance(exponent, int):
        return
    if abs(exponent) > _MAX_EXPONENT:
        raise ResultTooLargeError("exponent too large")
    if exponent <= 0:
        return
    if isinstance(base, int) and abs(base) > 1:
        # Conservative upper bound on the result's bit length.
        estimated_bits = exponent * abs(base).bit_length()
        if estimated_bits > _MAX_RESULT_BITS:
            raise ResultTooLargeError("result too large")
        # Also guard against results that cannot be printed by default.
        estimated_digits = exponent * math.log10(abs(base)) + 1
        if estimated_digits > _MAX_DECIMAL_DIGITS:
            raise ResultTooLargeError("result too large to print")


def _decimal_from_float(value: float) -> Decimal:
    """Convert a finite float to Decimal; reject inf/nan."""
    if not math.isfinite(value):
        raise ResultTooLargeError("numeric result too large")
    # str() yields the shortest decimal that round-trips through float.
    return Decimal(str(value))


def _power_op(base, exponent):
    """Compute base ** exponent, keeping ints exact and using Decimal/float otherwise."""
    # 0 raised to a negative exponent is division by zero.
    if base == 0 and exponent < 0:
        raise DivisionByZeroError("division by zero")

    # Treat whole-number Decimal exponents as integers.
    if isinstance(exponent, Decimal) and exponent == exponent.to_integral_value():
        exponent = int(exponent)

    # Both int: keep non-negative powers as int; compute negative powers with
    # Decimal division so we get exact decimal results instead of binary float
    # underflow/artifacts (e.g. 3^-1 == 0.333... rather than a float).
    if isinstance(base, int) and isinstance(exponent, int):
        if exponent >= 0:
            return base ** exponent
        positive_exp = -exponent
        _check_power_size(base, positive_exp)
        try:
            return Decimal(1) / (Decimal(base) ** positive_exp)
        except DecimalOverflow as exc:
            raise ResultTooLargeError("numeric result too large") from exc
        except (DecimalDivisionByZero, DecimalInvalidOperation) as exc:
            raise DivisionByZeroError("division by zero") from exc

    # Non-integer exponent: keep full Decimal precision (Python's decimal
    # module supports fractional powers via ln/exp).  Negative base with a
    # non-integer exponent has no real solution and raises
    # DecimalInvalidOperation; convert it to NonRealResultError to preserve the
    # same user-facing semantics the old float fallback had.
    if isinstance(exponent, Decimal):
        try:
            return Decimal(base) ** exponent
        except DecimalOverflow as exc:
            raise ResultTooLargeError("numeric result too large") from exc
        except DecimalInvalidOperation as exc:
            raise NonRealResultError("result is not a real number") from exc

    # exponent is int; base may be int or Decimal.
    if exponent == 0:
        # Consistent with Python's int**0 == 1, including 0**0.
        return Decimal(1) if isinstance(base, Decimal) else 1
    try:
        return Decimal(base) ** exponent
    except DecimalOverflow as exc:
        raise ResultTooLargeError("numeric result too large") from exc
    except (DecimalDivisionByZero, DecimalInvalidOperation) as exc:
        raise DivisionByZeroError("division by zero") from exc


def _guard_value(value):
    """Ensure a numeric value is safe to keep using and eventually print.

    Rejects non-real results, oversized integers, non-finite floats/Decimals,
    and Decimals with an absurdly large or small exponent. Called uniformly
    after every literal parse and every arithmetic operation.
    """
    if isinstance(value, bool):
        # bool is a subclass of int; it should never appear here, but reject
        # explicitly just in case.
        raise NonRealResultError("result is not a real number")
    if isinstance(value, (int, Decimal)):
        if isinstance(value, int):
            if value == 0:
                return value
            b = value.bit_length()
            lower_digits = int((b - 1) * _LOG10_2) + 1
            if lower_digits > _MAX_DECIMAL_DIGITS:
                raise ResultTooLargeError("result too large to print")
            upper_digits = int(b * _LOG10_2) + 1
            if upper_digits <= _MAX_DECIMAL_DIGITS:
                return value
            # Borderline case: value has at most upper_digits digits, which is
            # close to the limit, so converting it is safe.
            try:
                digit_count = len(str(abs(value)))
            except ValueError as exc:
                raise ResultTooLargeError("result too large to print") from exc
            if digit_count > _MAX_DECIMAL_DIGITS:
                raise ResultTooLargeError("result too large to print")
            return value

        # Decimal: scientific notation keeps even huge exponents compact, so we
        # only guard coefficient length and finiteness.  A generous exponent
        # magnitude bound prevents pathological cases.
        if not value.is_finite():
            raise ResultTooLargeError("numeric result too large")
        if value == 0:
            return value
        coeff_digits = len(value.as_tuple().digits)
        if coeff_digits > _MAX_DECIMAL_DIGITS:
            raise ResultTooLargeError("result too large to print")
        if abs(value.adjusted()) > _MAX_RESULT_BITS:
            raise ResultTooLargeError("result too large to print")
        return value

    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            raise ResultTooLargeError("numeric result too large")
        return value

    raise NonRealResultError("result is not a real number")


def _safe_op(func, *args, **kwargs):
    """Run an arithmetic operation and convert overflow to CalcError."""
    try:
        return func(*args, **kwargs)
    except (OverflowError, DecimalOverflow) as exc:
        raise ResultTooLargeError("numeric result too large") from exc


class _Parser:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.pos = 0
        self.depth = 0
        if not self.tokens:
            raise MalformedExpressionError("empty expression")

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

    def _peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _consume(self, expected_type: str | None = None):
        token = self._peek()
        if token is None:
            raise MalformedExpressionError("unexpected end of expression")
        if expected_type is not None and token[0] != expected_type:
            raise MalformedExpressionError(
                f"expected {expected_type}, got {token[1]!r}"
            )
        self.pos += 1
        return token

    def parse(self):
        result = self._expr()
        if self.pos != len(self.tokens):
            remaining = self._peek()
            raise MalformedExpressionError(f"unexpected token: {remaining[1]!r}")
        return result

    def _expr(self):
        result = self._term()
        while True:
            token = self._peek()
            if token is None:
                break
            if token[0] == "PLUS":
                self._consume("PLUS")
                rhs = self._term()
                result = _guard_value(_safe_op(lambda a, b: a + b, result, rhs))
            elif token[0] == "MINUS":
                self._consume("MINUS")
                rhs = self._term()
                result = _guard_value(_safe_op(lambda a, b: a - b, result, rhs))
            else:
                break
        return result

    def _term(self):
        result = self._unary()
        while True:
            token = self._peek()
            if token is None:
                break
            if token[0] == "MUL":
                self._consume("MUL")
                rhs = self._unary()
                result = _guard_value(_safe_op(lambda a, b: a * b, result, rhs))
            elif token[0] == "DIV":
                self._consume("DIV")
                divisor = self._unary()
                try:
                    result = _safe_op(
                        lambda a, b: Decimal(a) / Decimal(b), result, divisor
                    )
                except (DecimalDivisionByZero, DecimalInvalidOperation) as exc:
                    raise DivisionByZeroError("division by zero") from exc
                result = _guard_value(result)
            else:
                break
        return result

    def _unary(self):
        token = self._peek()
        if token is not None and token[0] == "PLUS":
            self._consume("PLUS")
            with self._nested():
                return _guard_value(_safe_op(lambda a: +a, self._unary()))
        if token is not None and token[0] == "MINUS":
            self._consume("MINUS")
            with self._nested():
                return _guard_value(_safe_op(lambda a: -a, self._unary()))
        return self._power()

    def _power(self):
        base = self._primary()
        token = self._peek()
        if token is not None and token[0] == "POW":
            self._consume("POW")
            with self._nested():
                exponent = self._unary()
            _check_power_size(base, exponent)
            result = _power_op(base, exponent)
            return _guard_value(result)
        return base

    def _primary(self):
        token = self._peek()
        if token is None:
            raise MalformedExpressionError("unexpected end of expression")
        if token[0] == "HEX":
            self._consume("HEX")
            value = token[1]
            hex_digits = value[2:]
            # Guard against allocating a huge int: each hex digit carries ~1.204
            # decimal digits. Reject before calling int(..., 16), which is not
            # protected by sys.set_int_max_str_digits() when a base is given.
            if len(hex_digits) * 1.21 > _MAX_DECIMAL_DIGITS:
                raise ResultTooLargeError("numeric literal too large")
            try:
                number = int(value, 16)
            except (ValueError, OverflowError) as exc:
                raise ResultTooLargeError("numeric literal too large") from exc
            return _guard_value(number)
        if token[0] == "NUMBER":
            self._consume("NUMBER")
            value = token[1]
            try:
                if "e" in value or "E" in value or "." in value:
                    number = Decimal(value)
                else:
                    # Avoid allocating a huge int just to reject it.
                    if len(value) > _MAX_DECIMAL_DIGITS:
                        raise ResultTooLargeError("numeric literal too large")
                    number = int(value)
            except (ValueError, OverflowError) as exc:
                raise ResultTooLargeError("numeric literal too large") from exc
            return _guard_value(number)
        if token[0] == "IDENT":
            self._consume("IDENT")
            name = token[1]
            if name in _CONSTANTS:
                return _guard_value(_CONSTANTS[name])
            if name not in _KNOWN_FUNCTIONS:
                raise MalformedExpressionError(f"unknown function: {name}")
            self._consume("LPAREN")
            with self._nested():
                arg = self._expr()
            self._consume("RPAREN")
            return _apply_function(name, arg)
        if token[0] == "LPAREN":
            self._consume("LPAREN")
            with self._nested():
                result = self._expr()
            self._consume("RPAREN")
            return result
        raise MalformedExpressionError(f"unexpected token: {token[1]!r}")


def calculate(expression: str):
    """Evaluate a simple arithmetic expression safely.

    Supports ``+``, ``-``, ``*``, ``/``, parentheses, and ``^`` for
    exponentiation.  Built-in functions are also supported:
    ``sqrt``, ``ln``, ``log10``, ``sin``, ``cos``, ``tan``
    (e.g. ``sqrt(2) + 3``).  The mathematical constants ``e`` and ``pi`` are
    recognized as bare identifiers (lowercase only).  Decimal literals may use
    scientific notation (``1e3``, ``1.5e-10``) and integer literals may use
    hexadecimal notation (``0x10``, ``0xFF``).  Function arguments are full
    expressions and may be nested.  ``sin``, ``cos``, and ``tan`` take radians
    and use standard
    float precision, unlike the rest of the calculator which uses exact
    ``decimal.Decimal`` arithmetic.  Whitespace is ignored.  Non-integer
    results use ``decimal.Decimal`` with the precision configured by
    ``decimal.getcontext().prec`` (28 significant digits by default).

    Args:
        expression: The arithmetic expression to evaluate.

    Returns:
        The numeric result (``int`` or ``decimal.Decimal``).

    Raises:
        MalformedExpressionError: If the expression is not valid or too long.
        DivisionByZeroError: If a division by zero occurs.
        ResultTooLargeError: If a result would be unreasonably large or
            impossible to print.
        NonRealResultError: If an operation would produce a non-real result.
    """
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise MalformedExpressionError("expression too long")
    tokens = list(_tokenize(expression))
    _check_paren_depth(tokens)
    result = _Parser(tokens).parse()
    return _guard_value(result)
