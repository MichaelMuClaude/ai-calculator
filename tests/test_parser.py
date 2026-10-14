from decimal import Decimal
import time

import pytest

from ai_calc.parser import (
    calculate,
    CalcError,
    DivisionByZeroError,
    MalformedExpressionError,
    NonRealResultError,
    ResultTooLargeError,
)


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("1 + 2", 3),
        ("5 - 3", 2),
        ("4 * 5", 20),
        ("8 / 2", 4.0),
        ("(1 + 2) * 3", 9),
        ("2 ^ 3", 8),
        ("2 + 3 * 4", 14),
        ("2 ^ 3 ^ 2", 512),  # right-associative exponentiation
        ("-5 + 3", -2),
        ("+5", 5),
        ("3.5 * 2", 7.0),
        ("  1  +   2  ", 3),
        ("5 * -2", -10),
        ("--5", 5),
        ("2^-3", 0.125),
        ("((2 + 3) * (4 - 1)) / 3", 5.0),
    ],
)
def test_calculate(expression, expected):
    assert calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "1 / 0",
        "1 / 0.0",
        "0 ^ -1",
    ],
)
def test_division_by_zero(expression):
    with pytest.raises(DivisionByZeroError):
        calculate(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "1 + * 2",
        "(1 + 2",
        "1 + 2)",
        "1 + a",
        "1 +",
        "* 2",
    ],
)
def test_malformed_expression(expression):
    with pytest.raises(MalformedExpressionError):
        calculate(expression)


def test_calc_error_is_base_class():
    assert issubclass(MalformedExpressionError, CalcError)
    assert issubclass(DivisionByZeroError, CalcError)
    assert issubclass(ResultTooLargeError, CalcError)
    assert issubclass(NonRealResultError, CalcError)


# Regression tests for reviewer findings


def test_exponent_too_large_is_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate("2 ^ 1000000000")


def test_power_tower_too_large_is_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate("9 ^ 9 ^ 9")


def test_power_result_too_large_to_print_is_rejected():
    # 2^(2^18) has ~78k decimal digits, which exceeds Python's default
    # int-to-string conversion limit (4300 digits).
    with pytest.raises(ResultTooLargeError):
        calculate("2 ^ 2 ^ 18")


def test_borderline_huge_int_is_rejected_as_result_too_large():
    # Regression: 10^4299 is exactly at Python's int-to-string limit, and
    # multiplying by 10 pushes it over. The guard must raise ResultTooLargeError
    # rather than letting ValueError from str() propagate.
    with pytest.raises(ResultTooLargeError):
        calculate("10 ^ 4299 * 10")


def test_deeply_nested_parentheses_raises_calc_error():
    expression = "(" * 2000 + "1" + ")" * 2000
    with pytest.raises(CalcError):
        calculate(expression)


def test_deeply_nested_parentheses_is_not_recursion_error():
    expression = "(" * 2000 + "1" + ")" * 2000
    with pytest.raises(MalformedExpressionError):
        calculate(expression)


def test_unary_minus_precedence_is_lower_than_power():
    assert calculate("-2 ^ 2") == -4
    assert calculate("-2 ^ 3") == -8
    assert calculate("-(2 ^ 2)") == -4


def test_unary_minus_still_works_in_exponent():
    assert calculate("2 ^ -3") == 0.125
    assert calculate("2 ^ -2") == 0.25


def test_parenthesized_negative_base_can_still_be_squared():
    assert calculate("(-2) ^ 2") == 4
    assert calculate("(-2) ^ 3") == -8


# Systematic size-guard regression tests


def test_oversized_literal_is_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate("9" * 5000)


def test_decimal_power_large_exponent_succeeds():
    # Decimal scientific notation keeps this compact and printable.
    assert calculate("10.0 ^ 400") == Decimal("1.0E+400")


def test_decimal_division_large_exponent_succeeds():
    # Decimal division no longer overflows to infinity the way float did.
    assert calculate("10 ^ 400 / 1") == Decimal("1.0E+400")


def test_decimal_integral_exponent_size_guard():
    # Decimal-typed integral exponents must not bypass the exponent size guard.
    with pytest.raises(ResultTooLargeError):
        calculate("2 ^ 1000000000000.0")


def test_decimal_non_integral_exponent_size_guard_and_overflow():
    # Non-integral Decimal exponents must be size-bounded; any Decimal overflow
    # (or the up-front size guard) must be converted to CalcError.
    with pytest.raises(ResultTooLargeError):
        calculate("10 ^ 1000000.5")


def test_decimal_non_integral_exponent_finite_result():
    # Non-integral exponents now stay in Decimal precision instead of falling
    # back to float.
    result = calculate("2 ^ 1000.5")
    assert isinstance(result, Decimal)
    assert result == Decimal(2) ** Decimal("1000.5")
    assert result != Decimal(str(2.0 ** 1000.5))


def test_decimal_integral_power_overflow_is_caught():
    # Decimal(base) ** exponent can raise decimal.Overflow for huge exponents.
    with pytest.raises(ResultTooLargeError):
        calculate("10.0 ^ 1000000")


def test_decimal_zero_to_zero_returns_one():
    # 0.0 ^ 0 must behave like 0 ^ 0 and return 1, not raise InvalidOperation.
    assert calculate("0.0 ^ 0") == 1
    assert calculate("0 ^ 0") == 1
    assert calculate("0.0 ^ 0.0") == 1


def test_negative_int_exponent_uses_decimal_not_float():
    # 3^-1 should be an exact repeating Decimal, not a binary-float artifact.
    result = calculate("3 ^ -1")
    assert result == Decimal("0.3333333333333333333333333333")
    assert isinstance(result, Decimal)


def test_large_negative_int_exponent_is_rejected_cleanly():
    # 2^-1000000 would require computing 2^1000000; reject cleanly rather than
    # silently underflowing to 0.0 as Python float would.
    with pytest.raises(ResultTooLargeError):
        calculate("2 ^ -1000000")


def test_intermediate_multiplication_chain_growth_is_rejected():
    # Each factor is small, but the running product grows past the print limit.
    with pytest.raises(ResultTooLargeError):
        calculate("2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000")


def test_addition_overflow_is_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate(f"{'9' * 4300} + {'9' * 4300}")


def test_subtraction_overflow_is_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate(f"{'9' * 4300} - -{'9' * 4300}")


def test_unary_minus_on_oversized_literal_is_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate("-" + "9" * 5000)


def test_expression_too_long_is_rejected():
    expression = "1+" * 6000  # 12000 characters
    with pytest.raises(MalformedExpressionError):
        calculate(expression)


def test_negative_base_fractional_exponent_is_rejected():
    # Real-number calculator: complex results are out of scope.
    with pytest.raises(NonRealResultError, match="result is not a real number"):
        calculate("(-1) ^ 0.5")


def test_negative_base_other_fractional_exponents():
    for expr in ["(-2) ^ 0.5", "(-1) ^ 0.25", "(-4) ^ 0.5", "(-8) ^ (1 / 3)"]:
        with pytest.raises(NonRealResultError, match="result is not a real number"):
            calculate(expr)


def test_non_negative_base_fractional_exponent_still_works():
    assert calculate("4 ^ 0.5") == 2.0
    assert calculate("9 ^ 0.5") == 3.0
    assert calculate("27 ^ (1 / 3)") == 3.0


def test_non_integral_exponent_uses_decimal_precision():
    # 2^0.5 must use Decimal's 28 significant digits, not 17-digit float.
    result = calculate("2 ^ 0.5")
    assert isinstance(result, Decimal)
    assert result == Decimal(2).sqrt()
    # Make sure it is not the old float-rounded value.
    assert result != Decimal(str(2.0 ** 0.5))


def test_sqrt_and_power_consistent_precision():
    # sqrt(2)^2 and (2^0.5)^2 should both have the same Decimal precision.
    sqrt_squared = calculate("sqrt(2) ^ 2")
    power_squared = calculate("(2 ^ 0.5) ^ 2")
    assert isinstance(sqrt_squared, Decimal)
    assert isinstance(power_squared, Decimal)
    assert sqrt_squared == power_squared
    # Both are 1 ulp below 2 due to rounding; difference is negligible.
    assert abs(sqrt_squared - 2) <= Decimal("1E-27")
    assert abs(power_squared - 2) <= Decimal("1E-27")


# Built-in function tests


def test_sqrt_basic():
    assert calculate("sqrt(4)") == 2
    assert calculate("sqrt(2)") == Decimal(2).sqrt()


def test_ln_basic():
    assert calculate("ln(1)") == 0
    assert calculate("ln(2)") == Decimal(2).ln()


def test_log10_basic():
    assert calculate("log10(10)") == 1
    assert calculate("log10(100)") == 2
    assert calculate("log10(2)") == Decimal(2).ln() / Decimal(10).ln()


def test_trig_basic():
    assert calculate("sin(0)") == 0
    assert calculate("cos(0)") == 1
    assert calculate("tan(0)") == 0


def test_function_argument_is_full_expression():
    assert calculate("sqrt(1 + 3)") == 2
    assert calculate("ln(2 * 2)") == Decimal(4).ln()
    assert calculate("log10(5 + 5)") == 1


def test_function_nesting():
    assert calculate("sqrt(sqrt(16))") == 2
    assert calculate("ln(sqrt(2.718281828459045))") == Decimal(
        "2.718281828459045"
    ).sqrt().ln()


def test_functions_compose_with_arithmetic():
    assert calculate("2 * sqrt(16)") == 8
    assert calculate("sqrt(9) + ln(1) * 5") == 3
    assert calculate("3 + sin(0)") == 3
    assert calculate("10 ^ log10(1000)") == Decimal(1000)


def test_unknown_function_rejected():
    with pytest.raises(MalformedExpressionError):
        calculate("foo(2)")


def test_function_domain_errors():
    with pytest.raises(NonRealResultError):
        calculate("sqrt(-1)")
    with pytest.raises(NonRealResultError):
        calculate("ln(0)")
    with pytest.raises(NonRealResultError):
        calculate("ln(-1)")
    with pytest.raises(NonRealResultError):
        calculate("log10(0)")
    with pytest.raises(NonRealResultError):
        calculate("log10(-1)")


def test_trig_huge_argument_overflow_is_caught():
    with pytest.raises(ResultTooLargeError):
        calculate("sin(10 ^ 400)")


def test_trig_decimal_overflows_to_inf_is_caught():
    # Decimal('1.0E+309') converts to float('inf') silently, which then makes
    # math.sin/cos/tan raise ValueError.  This must be a clean CalcError.
    for expr in ["sin(10.0 ^ 309)", "cos(10.0 ^ 309)", "tan(10.0 ^ 309)"]:
        with pytest.raises(CalcError):
            calculate(expr)


# Mathematical constants e and pi


def test_constants_pi_and_e_exact_values():
    # Both constants are defined with 28 significant digits to match the
    # calculator's default Decimal precision.
    assert calculate("pi") == Decimal("3.141592653589793238462643383")
    assert calculate("e") == Decimal("2.718281828459045235360287471")


def test_constants_participate_in_expressions():
    assert calculate("2 * pi") == 2 * Decimal("3.141592653589793238462643383")
    assert calculate("e ^ 2") == Decimal("2.718281828459045235360287471") ** 2
    assert calculate("sqrt(e)") == Decimal("2.718281828459045235360287471").sqrt()
    # ln(e) is limited by Decimal precision; with the 28-digit constant it is
    # 0.999... (28 digits), within 1 ulp of 1.
    assert abs(calculate("ln(e)") - 1) < Decimal("1E-27")


def test_constants_are_lowercase_only():
    # Design decision: only lowercase "e" and "pi" are constants; uppercase
    # variants remain unknown functions/identifiers.
    with pytest.raises(MalformedExpressionError, match="unknown function: E"):
        calculate("E")
    with pytest.raises(MalformedExpressionError, match="unknown function: PI"):
        calculate("PI")


# Scientific notation


def test_scientific_notation_decimal_literals():
    assert calculate("1e3") == 1000
    assert calculate("1.5e-2") == Decimal("0.015")
    assert calculate("2E+5") == 200000
    assert calculate("3.0e2") == Decimal("300")
    assert calculate(".5e2") == Decimal("50")


def test_scientific_notation_disambiguation():
    # "1e3" must be a single NUMBER token, not NUMBER("1") IDENT("e") NUMBER("3").
    assert calculate("1e3") == 1000
    # Bare "e" is still the constant.
    assert calculate("e") == Decimal("2.718281828459045235360287471")
    # Multiplication by the constant must work.
    assert calculate("2 * e") == 2 * Decimal("2.718281828459045235360287471")
    # "2e" without exponent digits is malformed (NUMBER("2") + IDENT("e")).
    with pytest.raises(MalformedExpressionError):
        calculate("2e")


def test_scientific_notation_huge_exponent_is_rejected():
    # A very compact literal can denote an astronomically large value; the
    # Decimal exponent guard must reject it.
    with pytest.raises(ResultTooLargeError):
        calculate("1e100000000")


# Hexadecimal integer literals


def test_hex_literals():
    assert calculate("0x10") == 16
    assert calculate("0xFF") == 255
    assert calculate("0xAb1F") == int("0xAb1F", 16)
    assert calculate("0X0") == 0


def test_hex_literal_too_large_is_rejected_fast():
    # int(hex_string, 16) is not protected by sys.set_int_max_str_digits(), so
    # the parser must reject by length before conversion. 5000 hex digits is far
    # above the decimal digit limit, so this should return instantly.
    huge_hex = "0x" + "f" * 5000
    start = time.perf_counter()
    with pytest.raises(ResultTooLargeError):
        calculate(huge_hex)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, "hex length pre-check should reject instantly"
