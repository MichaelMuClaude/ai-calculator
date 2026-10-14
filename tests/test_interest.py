from decimal import Decimal

import pytest

from ai_calc.interest import CompoundInterestError, calculate_compound_interest
from ai_calc.parser import ResultTooLargeError


def test_monthly_compounding():
    # 1000 at 5% annual, compounded monthly for 3 years.
    result = calculate_compound_interest("1000", "5", "12", "3")
    assert result == Decimal("1161.472231333468300531497363")


def test_annual_compounding():
    result = calculate_compound_interest("1000", "5", "1", "3")
    assert result == Decimal("1157.625000")


def test_daily_compounding():
    result = calculate_compound_interest("1000", "5", "365", "3")
    assert result == Decimal("1161.822307226404751531210033")


def test_zero_years_returns_principal():
    result = calculate_compound_interest("1500.50", "5", "12", "0")
    assert result == Decimal("1500.50")


def test_fractional_years():
    # 1000 at 5% annual, compounded monthly for 0.1 years (exponent = 1.2).
    result = calculate_compound_interest("1000", "5", "12", "0.1")
    expected = (
        Decimal("1000")
        * (Decimal("1") + Decimal("0.05") / Decimal("12")) ** Decimal("1.2")
    )
    assert result == expected



def test_depreciation_negative_rate():
    # 10% annual depreciation, compounded yearly for 2 years.
    result = calculate_compound_interest("1000", "-10", "1", "2")
    assert result == Decimal("810.000000")


def test_principal_must_be_positive():
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("0", "5", "12", "3")
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("-100", "5", "12", "3")


def test_times_per_year_must_be_positive_integer():
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "5", "0", "3")
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "5", "-12", "3")
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "5", "12.5", "3")


def test_years_must_be_non_negative():
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "5", "12", "-1")


def test_rate_too_negative_rejected():
    # r = -12, n = 12 -> r/n = -1 -> base = 0, which is invalid.
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "-1200", "12", "1")
    # r = -12.01, n = 12 -> r/n < -1 -> base < 0, invalid.
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "-1201", "12", "1")


def test_invalid_inputs_rejected():
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("abc", "5", "12", "3")
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "abc", "12", "3")
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "5", "abc", "3")
    with pytest.raises(CompoundInterestError):
        calculate_compound_interest("1000", "5", "12", "abc")


def test_very_large_result_rejected():
    # Large principal/rate/years combination should hit size guards.
    with pytest.raises(ResultTooLargeError):
        calculate_compound_interest("1" + "0" * 5000, "100", "1", "10")


def test_extreme_years_rejected():
    # An extreme exponent should be rejected by the same guard used by the
    # arithmetic parser's power operator.
    with pytest.raises(ResultTooLargeError):
        calculate_compound_interest("1000", "5", "12", "1000000000")

