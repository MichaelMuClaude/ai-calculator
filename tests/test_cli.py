import json
import os
import subprocess
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from ai_calc import __version__ as ai_calc_version
from ai_calc.cli import _format_currency, main


@pytest.fixture
def clean_cache(tmp_path, monkeypatch):
    """Use a temporary cache directory for currency-conversion tests."""
    monkeypatch.setattr("ai_calc.exchange._cache_dir", lambda: str(tmp_path / "cache"))
    from ai_calc.exchange import _save_cache

    _save_cache({})
    yield
    _save_cache({})


def test_cli_success(capsys):
    assert main(["2 + 2"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "4"
    assert captured.err == ""


def test_cli_with_parentheses(capsys):
    assert main(["(1 + 2) * 3"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "9"


def test_cli_division_by_zero(capsys):
    code = main(["1 / 0"])
    captured = capsys.readouterr()
    assert code == 1
    assert "division by zero" in captured.err.lower()


def test_cli_malformed_expression(capsys):
    code = main(["1 + * 2"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


@pytest.mark.parametrize("args", [["1", "+", "2"]])
def test_cli_usage_error(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    assert code == 2
    assert "Usage:" in captured.err


def test_cli_empty_argv_starts_repl(monkeypatch):
    calls = []

    def fake_run_repl():
        calls.append(True)
        return 0

    monkeypatch.setattr("ai_calc.cli.run_repl", fake_run_repl)
    code = main([])
    assert code == 0
    assert calls == [True]


def test_cli_result_too_large(capsys):
    code = main(["2 ^ 1000000000"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_result_too_large_to_print(capsys):
    # Regression: must raise CalcError instead of letting print() crash.
    code = main(["2 ^ 2 ^ 18"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_deeply_nested_parens_is_caught(capsys):
    expression = "(" * 2000 + "1" + ")" * 2000
    code = main([expression])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_unary_minus_precedence(capsys):
    assert main(["-2 ^ 2"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "-4"


@pytest.mark.parametrize(
    "expression",
    [
        "9" * 5000,  # oversized literal
        "2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000 * 2 ^ 2000",  # chain growth
    ],
)
def test_cli_size_guard_catches_all_paths(expression, capsys):
    code = main([expression])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_decimal_power_large_exponent_succeeds(capsys):
    assert main(["10.0 ^ 400"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "1.000000000000000000000000000E+400"
    assert captured.err == ""


def test_cli_decimal_division_large_exponent_succeeds(capsys):
    assert main(["10 ^ 400 / 1"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "1.000000000000000000000000000E+400"
    assert captured.err == ""


@pytest.mark.parametrize(
    "expression",
    [
        "2 ^ 1000000000000.0",
        "10 ^ 1000000.5",
    ],
)
def test_cli_decimal_exponent_guard(expression, capsys):
    code = main([expression])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


@pytest.mark.parametrize(
    "expression",
    [
        "(-1) ^ 0.5",
        "(-2) ^ 0.5",
        "(-1) ^ 0.25",
    ],
)
def test_cli_non_real_result_is_rejected(expression, capsys):
    code = main([expression])
    captured = capsys.readouterr()
    assert code == 1
    assert "not a real number" in captured.err.lower()


def test_cli_expression_too_long(capsys):
    code = main(["1+" * 6000])
    captured = capsys.readouterr()
    assert code == 1
    assert "too long" in captured.err.lower()


def test_cli_decimal_integral_power_overflow(capsys):
    code = main(["10.0 ^ 1000000"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_decimal_zero_to_zero(capsys):
    assert main(["0.0 ^ 0"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "1"


def test_cli_negative_int_exponent_exact_decimal(capsys):
    assert main(["3 ^ -1"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "0.3333333333333333333333333333"
    assert captured.err == ""


def test_cli_large_negative_int_exponent_rejected(capsys):
    code = main(["2 ^ -1000000"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


# Currency conversion CLI tests


def _mock_api_response(rate):
    response = MagicMock()
    response.status = 200
    response.read.return_value = json.dumps({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": rate},
    }).encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_cli_convert_success(capsys, clean_cache):
    with patch("ai_calc.exchange.urlopen", return_value=_mock_api_response(0.9234)):
        code = main(["--convert", "100", "USD", "EUR"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "92.3400"
    assert captured.err == ""


def test_cli_convert_usage_error(capsys):
    code = main(["--convert", "100", "USD"])
    captured = capsys.readouterr()
    assert code == 2
    assert "Usage:" in captured.err


def test_cli_convert_invalid_currency(capsys, clean_cache):
    code = main(["--convert", "100", "usd", "EUR"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_convert_network_error(capsys, clean_cache):
    from urllib.error import URLError
    with patch("ai_calc.exchange.urlopen", side_effect=URLError("down")):
        code = main(["--convert", "100", "USD", "EUR"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_compound_interest_success(capsys):
    code = main(["--compound-interest", "1000", "5", "12", "3"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "1161.47"
    assert captured.err == ""


def test_cli_compound_interest_long_decimal_rounded(capsys):
    # Regression: result used to print ~25 digits; now it is rounded to 2 dp.
    code = main(["--compound-interest", "100000", "7", "12", "10"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "200966.14"
    assert captured.err == ""


def test_cli_compound_interest_zero_years(capsys):
    code = main(["--compound-interest", "1500.50", "5", "12", "0"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "1500.50"


def test_cli_compound_interest_integer_result_shows_cents(capsys):
    # Zero years returns the principal unchanged; currency display must keep .00.
    code = main(["--compound-interest", "100", "0", "12", "0"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "100.00"
    assert captured.err == ""


def test_cli_compound_interest_rounds_half_up(capsys):
    # 100 * (1 + 0.005%/1)^1 == 100.005. ROUND_HALF_UP -> 100.01;
    # ROUND_HALF_EVEN would wrongly keep it as 100.00.
    code = main(["--compound-interest", "100", "0.005", "1", "1"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "100.01"
    assert captured.err == ""


def test_cli_compound_interest_result_too_large_to_print(capsys):
    # Regression: _format_currency can raise CalcError for extreme values.
    # Must be caught by the same try block as calculate_compound_interest.
    code = main(["--compound-interest", "1E+999999", "0", "1", "0"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")
    assert captured.out == ""


def test_format_currency_invalid_operation_raises_calc_error():
    from ai_calc.parser import ResultTooLargeError

    with pytest.raises(ResultTooLargeError):
        _format_currency(Decimal("1E+10000000"))


def test_cli_compound_interest_invalid_input(capsys):
    code = main(["--compound-interest", "-1000", "5", "12", "3"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("Error:")


def test_cli_compound_interest_usage_error(capsys):
    code = main(["--compound-interest", "1000", "5", "12"])
    captured = capsys.readouterr()
    assert code == 2
    assert "Usage:" in captured.err


# Typoed single-argument flags and --version


@pytest.mark.parametrize("flag", ["--hepl", "--conver", "--fractoin", "--convertt"])
def test_cli_unknown_single_option_is_usage_error(flag, capsys):
    """A single argument that looks like a mistyped flag must be a usage error."""
    code = main([flag])
    captured = capsys.readouterr()
    assert code == 2
    assert f"unknown option: '{flag}'" in captured.err
    assert "Usage:" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("expression, expected", [
    ("--5", "5"),
    ("--(2+3)", "5"),
])
def test_cli_double_unary_minus_still_valid(expression, expected, capsys):
    """--5 and --(2+3) are valid arithmetic, not typos."""
    code = main([expression])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == expected
    assert captured.err == ""


def test_cli_version(capsys):
    code = main(["--version"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == f"ai-calc {ai_calc_version}"
    assert captured.err == ""


def test_cli_help_includes_new_features(capsys):
    code = main(["--help"])
    captured = capsys.readouterr()
    assert code == 0
    assert "--version" in captured.out
    assert "pi" in captured.out
    assert "scientific" in captured.out
    assert "hex" in captured.out


class TestLocaleRegression:
    def test_main_does_not_crash_under_non_utf8_locale(self):
        """Regression test: stdout writes (including Chinese date output)
        must not raise UnicodeEncodeError when stdout is redirected under a
        non-UTF-8 locale.
        """
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        env["PYTHONUTF8"] = "0"
        env["PYTHONPATH"] = os.pathsep.join(
            ["src"] + env.get("PYTHONPATH", "").split(os.pathsep)
        )

        result = subprocess.run(
            [sys.executable, "-m", "ai_calc.cli", "--date", "2026-01-01 - 2026-01-01"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )

        assert result.returncode in (0, 1, 2), (
            f"Unexpected exit code {result.returncode}; stderr:\n{result.stderr}"
        )
        assert "UnicodeEncodeError" not in result.stderr, (
            f"UnicodeEncodeError traceback found in stderr:\n{result.stderr}"
        )
