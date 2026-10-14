import time

import pytest
from fractions import Fraction

from ai_calc.cli import main
from ai_calc.fraction_calc import calculate_fraction, format_fraction
from ai_calc.parser import (
    CalcError,
    DivisionByZeroError,
    MalformedExpressionError,
    ResultTooLargeError,
    _MAX_DECIMAL_DIGITS,
)


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("1/3 + 1/6", Fraction(1, 2)),
        ("(2/3)^3", Fraction(8, 27)),
        ("0.5 + 1/3", Fraction(5, 6)),
        ("2 * 3/4", Fraction(3, 2)),
        ("3/4 - 1/4", Fraction(1, 2)),
        ("--5", Fraction(5, 1)),
        ("+3/2", Fraction(3, 2)),
        ("-2^2", Fraction(-4, 1)),  # unary minus has lower precedence than ^
        ("(-2)^2", Fraction(4, 1)),
        ("1/2/3", Fraction(1, 6)),  # left-associative division
    ],
)
def test_calculate_fraction_basic_arithmetic(expression, expected):
    assert calculate_fraction(expression) == expected


def test_fraction_negative_integer_exponent():
    assert calculate_fraction("(1/2)^-1") == Fraction(2, 1)
    assert calculate_fraction("3^-2") == Fraction(1, 9)


def test_fraction_integer_result_formatting():
    # 4/2 reduces to 2/1 and should print as "2", not "2/1".
    value = calculate_fraction("4/2")
    assert value == Fraction(2, 1)
    assert format_fraction(value) == "2"


def test_fraction_negative_result_formatting():
    value = calculate_fraction("-1/3")
    assert value == Fraction(-1, 3)
    assert format_fraction(value) == "-1/3"
    # Sign normalization should also hold for 1/-3.
    assert format_fraction(calculate_fraction("1/-3")) == "-1/3"


@pytest.mark.parametrize(
    "expression",
    [
        "1/0",
        "1/(2-2)",  # subtraction yields zero divisor
        "0^-1",
    ],
)
def test_fraction_division_by_zero(expression):
    with pytest.raises(DivisionByZeroError):
        calculate_fraction(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "(1/2)^0.5",
        "2^0.5",
        "2^(1/2)",
        "(1/3)^-0.5",
    ],
)
def test_fraction_non_integer_exponent_rejected(expression):
    with pytest.raises(MalformedExpressionError):
        calculate_fraction(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "sqrt(2)",
        "ln(2)",
        "sin(1/2)",
        "foo(1)",
    ],
)
def test_fraction_builtin_functions_rejected(expression):
    with pytest.raises(MalformedExpressionError):
        calculate_fraction(expression)


def test_fraction_exponent_too_large():
    with pytest.raises(ResultTooLargeError):
        calculate_fraction("2^1000000000")


def test_fraction_negative_exponent_too_large():
    with pytest.raises(ResultTooLargeError):
        calculate_fraction("2^-1000000000")


def test_fraction_chain_growth_is_guarded():
    """A long sum of unit fractions with coprime denominators grows the common
    denominator past the safe print limit; the per-step guard must catch it.
    """

    def _primes_upto(n: int):
        sieve = [True] * (n + 1)
        sieve[0] = sieve[1] = False
        for i in range(2, int(n**0.5) + 1):
            if sieve[i]:
                step = i
                start = i * i
                sieve[start : n + 1 : step] = [False] * (
                    ((n - start) // step) + 1
                )
        return [i for i, is_prime in enumerate(sieve) if is_prime]

    primes = _primes_upto(10_100)
    expression = "+".join(f"1/{p}" for p in primes)
    with pytest.raises(ResultTooLargeError):
        calculate_fraction(expression)


def test_fraction_deeply_nested_parentheses_is_not_recursion_error():
    expression = "(" * 2000 + "1" + ")" * 2000
    with pytest.raises(MalformedExpressionError):
        calculate_fraction(expression)


def test_fraction_expression_too_long():
    expression = "1+" * 6000  # 12000 characters
    with pytest.raises(MalformedExpressionError):
        calculate_fraction(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "1 + * 2",
        "(1 + 2",
        "1 + 2)",
        "1 +",
    ],
)
def test_fraction_malformed_expression(expression):
    with pytest.raises(MalformedExpressionError):
        calculate_fraction(expression)


def test_fraction_errors_inherit_from_calc_error():
    assert issubclass(DivisionByZeroError, CalcError)
    assert issubclass(MalformedExpressionError, CalcError)
    assert issubclass(ResultTooLargeError, CalcError)


# CLI tests for the --fraction subcommand


def test_cli_fraction_success(capsys):
    code = main(["--fraction", "1/3 + 1/6"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "1/2"
    assert captured.err == ""


def test_cli_fraction_negative_exponent(capsys):
    code = main(["--fraction", "(1/2)^-1"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "2"


def test_cli_fraction_decimal_literal(capsys):
    code = main(["--fraction", "0.5 + 1/3"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "5/6"


def test_cli_fraction_division_by_zero(capsys):
    code = main(["--fraction", "1/0"])
    captured = capsys.readouterr()
    assert code == 1
    assert "division by zero" in captured.err.lower()


def test_cli_fraction_non_integer_exponent(capsys):
    code = main(["--fraction", "(1/2)^0.5"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_fraction_function_rejected(capsys):
    code = main(["--fraction", "sqrt(2)"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_fraction_usage_error(capsys):
    code = main(["--fraction"])
    captured = capsys.readouterr()
    assert code == 2
    assert "Usage:" in captured.err


def test_cli_fraction_chain_growth(capsys):
    def _primes_upto(n: int):
        sieve = [True] * (n + 1)
        sieve[0] = sieve[1] = False
        for i in range(2, int(n**0.5) + 1):
            if sieve[i]:
                step = i
                start = i * i
                sieve[start : n + 1 : step] = [False] * (
                    ((n - start) // step) + 1
                )
        return [i for i, is_prime in enumerate(sieve) if is_prime]

    primes = _primes_upto(10_100)
    expression = "+".join(f"1/{p}" for p in primes)
    code = main(["--fraction", expression])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_fraction_numeric_literal_too_large():
    """Overly long numeric literals must raise CalcError, not a raw ValueError."""
    huge_int = "9" * (_MAX_DECIMAL_DIGITS + 1000)
    huge_decimal = "0." + "9" * (_MAX_DECIMAL_DIGITS + 1000)
    with pytest.raises(ResultTooLargeError):
        calculate_fraction(huge_int)
    with pytest.raises(ResultTooLargeError):
        calculate_fraction(huge_decimal)


def test_fraction_huge_positive_exponent_rejected_quickly():
    """A pathologically large positive exponent must be rejected *before*
    Fraction() attempts to expand the Decimal into full integers.
    """
    start = time.perf_counter()
    with pytest.raises(ResultTooLargeError):
        calculate_fraction("1e100000000")
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0


def test_fraction_huge_negative_exponent_rejected_quickly():
    """A pathologically large negative exponent has the same absolute scale
    and must also be rejected quickly.
    """
    start = time.perf_counter()
    with pytest.raises(ResultTooLargeError):
        calculate_fraction("1e-100000000")
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("1e3", Fraction(1000, 1)),
        ("1.5e-10", Fraction(3, 20000000000)),
    ],
)
def test_fraction_scientific_notation_still_works(expression, expected):
    assert calculate_fraction(expression) == expected
