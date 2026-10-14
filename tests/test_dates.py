"""Tests for the ``--date`` date calculation mode."""

import datetime

import pytest

from ai_calc.cli import main
from ai_calc.date_calc import DateCalcError, _today, calculate_date
from ai_calc.parser import MalformedExpressionError, ResultTooLargeError


FIXED_TODAY = datetime.date(2031, 4, 15)


# ---------------------------------------------------------------------------
# Module-level date expression tests
# ---------------------------------------------------------------------------


def test_today_plus_days(monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    assert calculate_date("today + 30") == "2031-05-15"


def test_today_minus_days(monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    assert calculate_date("today - 45") == "2031-03-01"


def test_today_with_negative_offset(monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    # today + (-30) == today - 30
    assert calculate_date("today + -30") == "2031-03-16"


def test_today_with_double_negative_offset(monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    # today - (-30) == today + 30
    assert calculate_date("today - -30") == "2031-05-15"


def test_date_literal_plus_days():
    assert calculate_date("2026-07-07 + 30") == "2026-08-06"


def test_date_literal_minus_days():
    assert calculate_date("2026-07-07 - 45") == "2026-05-23"


def test_date_minus_date_future():
    assert calculate_date("2026-12-25 - 2026-07-07") == "171 天"


def test_date_minus_date_past():
    assert calculate_date("2026-07-07 - 2026-12-25") == "-171 天"


def test_today_minus_date(monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    assert calculate_date("today - 2031-01-01") == "104 天"


def test_date_minus_today(monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    assert calculate_date("2031-12-25 - today") == "254 天"


def test_whitespace_is_ignored():
    assert calculate_date("  2026-07-07  +  30  ") == "2026-08-06"


def test_no_spaces_around_operator():
    assert calculate_date("2026-07-07+30") == "2026-08-06"
    assert calculate_date("2026-12-25-2026-07-07") == "171 天"


def test_today_function_is_monkeypatchable():
    # Directly verify that ``_today`` is the single source of "now".
    assert _today() == datetime.date.today()


# ---------------------------------------------------------------------------
# Invalid date literals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "2026-13-45",  # month and day out of range
        "2026-02-30",  # February has no 30th
        "2026-04-31",  # April has 30 days
        "0000-01-01",  # year 0 is not a valid Gregorian date
    ],
)
def test_invalid_calendar_date(value):
    # The literal matches ``YYYY-MM-DD`` form but fails calendar validation.
    with pytest.raises(DateCalcError, match="invalid date"):
        calculate_date(f"{value} + 1")


@pytest.mark.parametrize(
    "value",
    [
        "2026-2-03",   # month must be zero-padded
        "2026-07-7",   # day must be zero-padded
        "07-07-2026",  # wrong component order
        "not-a-date",
        "2026/07/07",
    ],
)
def test_malformed_date_string(value):
    # The literal does not even look like ``YYYY-MM-DD``.
    with pytest.raises(MalformedExpressionError):
        calculate_date(f"{value} + 1")


# ---------------------------------------------------------------------------
# Out-of-range arithmetic
# ---------------------------------------------------------------------------


def test_add_extremely_large_days_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate_date("2026-07-07 + 99999999999")


def test_subtract_extremely_large_days_rejected():
    with pytest.raises(ResultTooLargeError):
        calculate_date("2026-07-07 - 99999999999")


# ---------------------------------------------------------------------------
# Invalid / malformed expressions
# ---------------------------------------------------------------------------


def test_empty_expression():
    with pytest.raises(MalformedExpressionError):
        calculate_date("")


def test_whitespace_only_expression():
    with pytest.raises(MalformedExpressionError):
        calculate_date("   ")


def test_bare_date_without_operator():
    with pytest.raises(MalformedExpressionError, match="incomplete date expression"):
        calculate_date("2026-07-07")


def test_bare_today_without_operator(monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    with pytest.raises(MalformedExpressionError, match="incomplete date expression"):
        calculate_date("today")


def test_multiplication_not_supported():
    with pytest.raises(MalformedExpressionError):
        calculate_date("2026-07-07 * 30")


def test_division_not_supported():
    with pytest.raises(MalformedExpressionError):
        calculate_date("2026-07-07 / 30")


def test_power_not_supported():
    with pytest.raises(MalformedExpressionError):
        calculate_date("2026-07-07 ^ 30")


def test_adding_dates_not_supported():
    with pytest.raises(MalformedExpressionError, match="adding two dates"):
        calculate_date("2026-07-07 + 2026-08-06")


def test_days_on_left_not_supported():
    with pytest.raises(MalformedExpressionError):
        calculate_date("30 + 2026-07-07")


def test_multiple_operators_not_supported():
    with pytest.raises(MalformedExpressionError):
        calculate_date("2026-07-07 + 30 + 1")


def test_trailing_garbage_rejected():
    with pytest.raises(MalformedExpressionError):
        calculate_date("2026-07-07 + 30 abc")


def test_expression_too_long():
    with pytest.raises(MalformedExpressionError, match="too long"):
        calculate_date("2026-07-07 + " + "9" * 20000)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_date_success(capsys, monkeypatch):
    monkeypatch.setattr("ai_calc.date_calc._today", lambda: FIXED_TODAY)
    code = main(["--date", "today + 30"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "2031-05-15"
    assert captured.err == ""


def test_cli_date_difference(capsys):
    code = main(["--date", "2026-12-25 - 2026-07-07"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "171 天"
    assert captured.err == ""


def test_cli_date_invalid_literal(capsys):
    code = main(["--date", "2026-13-45 + 1"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")
    assert "invalid date" in captured.err


def test_cli_date_out_of_range(capsys):
    code = main(["--date", "2026-07-07 + 99999999999"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_date_usage_error(capsys):
    code = main(["--date"])
    captured = capsys.readouterr()
    assert code == 2
    assert "Usage:" in captured.err


def test_cli_date_unknown_option_still_usage_error(capsys):
    # A single argument that looks like a mistyped flag must still be a usage
    # error, not a calculation error.
    code = main(["--dtae"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown option" in captured.err
