"""Currency exchange-rate conversion using the Frankfurter ECB API.

Rates are fetched from https://api.frankfurter.app/ (no API key required,
European Central Bank rates updated once per business day) and cached locally
for 24 hours.

Cache location:
- Linux: ~/.cache/ai-calc/rates.json
- macOS: ~/Library/Caches/ai-calc/rates.json
- Windows: %LOCALAPPDATA%\\ai-calc\\rates.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from decimal import Decimal
from decimal import InvalidOperation as DecimalInvalidOperation
from decimal import Overflow as DecimalOverflow
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .parser import CalcError, ResultTooLargeError, _guard_value


class ExchangeRateError(CalcError):
    """Raised when an exchange-rate lookup or conversion fails."""


API_BASE = "https://api.frankfurter.app/latest"
CACHE_TTL_SECONDS = 24 * 60 * 60
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _cache_dir() -> str:
    """Return the platform-appropriate cache directory for ai-calc."""
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches/ai-calc")
    if sys.platform == "win32":
        return os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local")),
            "ai-calc",
        )
    return os.path.expanduser("~/.cache/ai-calc")


def _cache_file() -> str:
    return os.path.join(_cache_dir(), "rates.json")


def _load_cache() -> dict:
    path = _cache_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    # Defensive: if the file is valid JSON but the wrong shape, treat it as
    # empty and re-fetch fresh rates rather than crashing.
    return data if isinstance(data, dict) else {}


def _save_cache(cache: dict) -> None:
    path = _cache_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError:
        # Cache write failures are non-fatal; we just fetch again next time.
        pass


def _validate_currency_code(code: str) -> None:
    if not isinstance(code, str) or not _CURRENCY_RE.match(code):
        raise ExchangeRateError(f"invalid currency code: {code!r}")


def _fetch_rate(from_code: str, to_code: str) -> Decimal:
    url = f"{API_BASE}?from={from_code}&to={to_code}"
    try:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "ai-calc/0.1.0",
            },
        )
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise ExchangeRateError("exchange rate service unavailable")
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise ExchangeRateError(
                f"unknown currency code: {from_code!r} or {to_code!r}"
            ) from exc
        raise ExchangeRateError("exchange rate service unavailable") from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise ExchangeRateError("exchange rate service unavailable") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExchangeRateError("exchange rate service returned invalid data") from exc

    try:
        rates = data["rates"]
        rate_value = rates[to_code]
    except (KeyError, TypeError) as exc:
        raise ExchangeRateError("exchange rate service returned invalid data") from exc

    try:
        rate = Decimal(str(rate_value))
    except Exception as exc:
        raise ExchangeRateError("exchange rate service returned invalid data") from exc
    if not rate.is_finite() or rate <= 0:
        raise ExchangeRateError("exchange rate service returned invalid data")
    return rate


def _get_rate(from_code: str, to_code: str) -> Decimal:
    now = time.time()
    cache = _load_cache()
    key = f"{from_code}:{to_code}"
    entry = cache.get(key) if isinstance(cache, dict) else None
    if isinstance(entry, dict):
        try:
            timestamp = float(entry["timestamp"])
            rate = Decimal(str(entry["rate"]))
            if (
                rate.is_finite()
                and rate > 0
                and 0 <= now - timestamp < CACHE_TTL_SECONDS
            ):
                return rate
        except (KeyError, TypeError, ValueError, DecimalInvalidOperation):
            # Corrupt entry; fetch fresh.
            pass

    rate = _fetch_rate(from_code, to_code)
    cache[key] = {"rate": str(rate), "timestamp": now}
    _save_cache(cache)
    return rate


def convert(amount_str: str, from_code: str, to_code: str):
    """Convert an amount from one currency to another.

    Args:
        amount_str: The amount to convert, as a decimal string.
        from_code: Source ISO 4217 currency code (3 uppercase letters).
        to_code: Target ISO 4217 currency code (3 uppercase letters).

    Returns:
        The converted amount as a ``Decimal``.

    Raises:
        ExchangeRateError: On validation, network, or API failure.
        ResultTooLargeError: If the result exceeds arithmetic size limits.
    """
    _validate_currency_code(from_code)
    _validate_currency_code(to_code)

    try:
        amount = Decimal(amount_str)
    except Exception as exc:
        raise ExchangeRateError(f"invalid amount: {amount_str!r}") from exc

    # Reject oversized amounts before multiplying, matching the arithmetic path.
    amount = _guard_value(amount)

    # Same-currency conversion is always 1:1; no network call needed.
    if from_code == to_code:
        return amount

    rate = _get_rate(from_code, to_code)
    try:
        result = amount * rate
    except (DecimalOverflow, DecimalInvalidOperation) as exc:
        raise ResultTooLargeError("numeric result too large") from exc
    return _guard_value(result)
