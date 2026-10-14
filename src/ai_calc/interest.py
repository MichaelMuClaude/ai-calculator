"""Compound-interest calculator.

Formula: A = P * (1 + r/n)^(n*t)

- P = principal (must be positive)
- r = annual interest rate as a percentage (e.g. 5 for 5%, not 0.05)
- n = number of times interest is compounded per year (positive integer)
- t = number of years (non-negative)

All arithmetic uses ``decimal.Decimal`` for exact decimal results.
"""

from __future__ import annotations

from decimal import Decimal
from decimal import DivisionByZero as DecimalDivisionByZero
from decimal import InvalidOperation as DecimalInvalidOperation
from decimal import Overflow as DecimalOverflow

from .parser import (
    CalcError,
    ResultTooLargeError,
    _check_power_size,
    _guard_value,
)


class CompoundInterestError(CalcError):
    """Raised when compound-interest inputs or computation are invalid."""


def _parse_positive_decimal(name: str, value: str) -> Decimal:
    try:
        d = Decimal(value)
    except Exception as exc:
        raise CompoundInterestError(f"invalid {name}: {value!r}") from exc
    d = _guard_value(d)
    if d <= 0:
        raise CompoundInterestError(f"{name} must be positive")
    return d


def _parse_non_negative_decimal(name: str, value: str) -> Decimal:
    try:
        d = Decimal(value)
    except Exception as exc:
        raise CompoundInterestError(f"invalid {name}: {value!r}") from exc
    d = _guard_value(d)
    if d < 0:
        raise CompoundInterestError(f"{name} must be non-negative")
    return d


def _parse_positive_int(name: str, value: str) -> int:
    try:
        d = Decimal(value)
    except Exception as exc:
        raise CompoundInterestError(f"invalid {name}: {value!r}") from exc
    d = _guard_value(d)
    if d != d.to_integral_value() or d <= 0:
        raise CompoundInterestError(f"{name} must be a positive integer")
    return int(d)


def calculate_compound_interest(
    principal_str: str,
    rate_percent_str: str,
    times_per_year_str: str,
    years_str: str,
) -> Decimal:
    """Calculate the final amount for compound interest.

    Args:
        principal_str: Principal amount (must be positive).
        rate_percent_str: Annual interest rate in percent (e.g. "5" for 5%).
            May be negative for depreciation, but must keep (1 + r/n) positive.
        times_per_year_str: Compounding frequency per year (positive integer).
        years_str: Number of years (non-negative).

    Returns:
        The final amount ``A`` as a ``Decimal``.

    Raises:
        CompoundInterestError: If any input is invalid or (1 + r/n) <= 0.
        ResultTooLargeError: If the intermediate/final result is too large.
    """
    principal = _parse_positive_decimal("principal", principal_str)
    times_per_year = _parse_positive_int("times_per_year", times_per_year_str)
    years = _parse_non_negative_decimal("years", years_str)

    # Zero years means no growth; return the principal unchanged.
    if years == 0:
        return principal

    try:
        rate_percent = Decimal(rate_percent_str)
    except Exception as exc:
        raise CompoundInterestError(f"invalid rate_percent: {rate_percent_str!r}") from exc
    rate_percent = _guard_value(rate_percent)

    # r is the decimal rate (e.g. 5% -> 0.05).
    r = rate_percent / Decimal(100)
    n = Decimal(times_per_year)
    base = Decimal(1) + r / n

    if base <= 0:
        raise CompoundInterestError(
            "rate_percent is too negative; (1 + rate/n) must be positive"
        )

    exponent = n * years

    # Apply the same exponent-size guard used by the arithmetic engine.
    _check_power_size(base, exponent)

    # Compute the power directly in Decimal to preserve precision for fractional
    # exponents (now also what the arithmetic engine's _power_op does internally).
    try:
        factor = base ** exponent
    except DecimalOverflow as exc:
        raise ResultTooLargeError("numeric result too large") from exc
    except (DecimalDivisionByZero, DecimalInvalidOperation) as exc:
        raise CompoundInterestError("invalid compounding factor") from exc
    factor = _guard_value(factor)

    try:
        result = principal * factor
    except (DecimalOverflow, DecimalInvalidOperation) as exc:
        raise ResultTooLargeError("numeric result too large") from exc
    return _guard_value(result)
