import json
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from ai_calc.exchange import (
    CACHE_TTL_SECONDS,
    ExchangeRateError,
    convert,
    _cache_file,
    _load_cache,
    _save_cache,
)
from ai_calc.parser import ResultTooLargeError


@pytest.fixture
def clean_cache(tmp_path, monkeypatch):
    """Use a temporary cache directory for each test."""
    monkeypatch.setattr("ai_calc.exchange._cache_dir", lambda: str(tmp_path / "cache"))
    _save_cache({})
    yield
    _save_cache({})


def _mock_response(payload, status=200):
    response = MagicMock()
    response.status = status
    response.read.return_value = (
        json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload
    )
    # MagicMock's default context manager returns a new mock; make it return
    # the same object so response.status is visible inside the `with` block.
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_successful_conversion(clean_cache):
    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": 0.9234},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response):
        result = convert("100", "USD", "EUR")

    assert result == Decimal("92.34")


def test_cache_hit_does_not_call_network(clean_cache):
    cache = {"USD:EUR": {"rate": "0.9234", "timestamp": time.time()}}
    _save_cache(cache)

    with patch("ai_calc.exchange.urlopen") as mock_urlopen:
        result = convert("100", "USD", "EUR")
        mock_urlopen.assert_not_called()

    assert result == Decimal("92.34")


def test_cache_expired_calls_network(clean_cache):
    stale_rate = "0.5000"
    cache = {
        "USD:EUR": {
            "rate": stale_rate,
            "timestamp": time.time() - CACHE_TTL_SECONDS - 1,
        }
    }
    _save_cache(cache)

    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-02",
        "rates": {"EUR": 0.9234},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response):
        result = convert("100", "USD", "EUR")

    assert result == Decimal("92.34")
    updated = _load_cache()
    assert updated["USD:EUR"]["rate"] == "0.9234"
    assert updated["USD:EUR"]["timestamp"] > float(cache["USD:EUR"]["timestamp"])


def test_network_failure_raises_exchange_rate_error(clean_cache):
    with patch("ai_calc.exchange.urlopen", side_effect=URLError("network down")):
        with pytest.raises(ExchangeRateError):
            convert("100", "USD", "EUR")


def test_invalid_currency_code_format_is_rejected_before_network_call(clean_cache):
    with patch("ai_calc.exchange.urlopen") as mock_urlopen:
        with pytest.raises(ExchangeRateError):
            convert("100", "usd", "EUR")
        mock_urlopen.assert_not_called()

    with patch("ai_calc.exchange.urlopen") as mock_urlopen:
        with pytest.raises(ExchangeRateError):
            convert("100", "USD", "EURO")
        mock_urlopen.assert_not_called()


def test_malformed_api_response_raises_exchange_rate_error(clean_cache):
    response = _mock_response(b"not json")

    with patch("ai_calc.exchange.urlopen", return_value=response):
        with pytest.raises(ExchangeRateError):
            convert("100", "USD", "EUR")


def test_missing_rate_in_api_response_raises_exchange_rate_error(clean_cache):
    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"GBP": 0.79},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response):
        with pytest.raises(ExchangeRateError):
            convert("100", "USD", "EUR")


def test_non_200_status_raises_exchange_rate_error(clean_cache):
    response = _mock_response({"error": "not found"}, status=404)

    with patch("ai_calc.exchange.urlopen", return_value=response):
        with pytest.raises(ExchangeRateError):
            convert("100", "USD", "EUR")


def test_http_error_404_unknown_currency(clean_cache):
    error = HTTPError("https://api.frankfurter.app/latest", 404, "not found", {}, None)
    with patch("ai_calc.exchange.urlopen", side_effect=error):
        with pytest.raises(ExchangeRateError, match="unknown currency code"):
            convert("100", "USD", "XYZ")


def test_http_error_non_404_still_service_unavailable(clean_cache):
    error = HTTPError("https://api.frankfurter.app/latest", 500, "server error", {}, None)
    with patch("ai_calc.exchange.urlopen", side_effect=error):
        with pytest.raises(ExchangeRateError, match="exchange rate service unavailable"):
            convert("100", "USD", "EUR")


def test_url_error_service_unavailable(clean_cache):
    with patch("ai_calc.exchange.urlopen", side_effect=URLError("network down")):
        with pytest.raises(ExchangeRateError, match="exchange rate service unavailable"):
            convert("100", "USD", "EUR")


def test_request_includes_user_agent(clean_cache):
    from urllib.request import Request

    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": 0.9234},
    })

    with patch("ai_calc.exchange.urlopen") as mock_urlopen:
        mock_urlopen.return_value = response
        convert("100", "USD", "EUR")
        request = mock_urlopen.call_args[0][0]
        assert isinstance(request, Request)
        assert request.get_header("User-agent") == "ai-calc/0.1.0"


@pytest.mark.parametrize(
    "bad_cache",
    [
        [],  # valid JSON, wrong shape (list)
        None,  # valid JSON, wrong shape (null)
        {"USD:EUR": []},  # entry is not a dict
        {"USD:EUR": {"timestamp": "now", "rate": "0.9234"}},  # bad timestamp
        {"USD:EUR": {"timestamp": time.time(), "rate": "not-a-number"}},  # bad rate
        {"USD:EUR": {"timestamp": time.time()}},  # missing rate
    ],
)
def test_malformed_cache_treated_as_miss(bad_cache, clean_cache):
    # Any malformed cache content should fall through to a fresh fetch.
    _save_cache(bad_cache)

    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": 0.9234},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response) as mock_urlopen:
        result = convert("100", "USD", "EUR")
        mock_urlopen.assert_called_once()

    assert result == Decimal("92.34")


def test_oversized_amount_rejected_before_multiplication(clean_cache):
    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": 0.9234},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response):
        with pytest.raises(ResultTooLargeError):
            convert("9" * 5000, "USD", "EUR")


def test_multiplication_overflow_is_caught(clean_cache):
    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": "1E+1000000"},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response):
        with pytest.raises(ResultTooLargeError):
            convert("1E+1000000", "USD", "EUR")


def test_same_currency_conversion_skips_network(clean_cache):
    with patch("ai_calc.exchange.urlopen") as mock_urlopen:
        result = convert("100.50", "USD", "USD")
        mock_urlopen.assert_not_called()
    assert result == Decimal("100.50")


@pytest.mark.parametrize("bad_rate", [0, 0.0, -1.5, "-0.9234"])
def test_non_positive_rate_from_api_is_rejected(bad_rate, clean_cache):
    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": bad_rate},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response):
        with pytest.raises(ExchangeRateError):
            convert("100", "USD", "EUR")


def test_non_positive_rate_from_cache_is_rejected(clean_cache):
    cache = {
        "USD:EUR": {"rate": "-0.9234", "timestamp": time.time()},
    }
    _save_cache(cache)

    response = _mock_response({
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-01",
        "rates": {"EUR": 0.9234},
    })

    with patch("ai_calc.exchange.urlopen", return_value=response):
        # Cache entry is rejected, so it fetches fresh and succeeds.
        result = convert("100", "USD", "EUR")

    assert result == Decimal("92.34")
