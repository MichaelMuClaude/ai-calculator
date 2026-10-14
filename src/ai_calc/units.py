"""Offline physical unit conversion.

Converts amounts between fixed physical units for length, mass, volume, and
temperature.  All conversions use ``decimal.Decimal``; no network access or
caching is required because the conversion factors are constants.
"""

from __future__ import annotations

from decimal import Decimal
from decimal import DivisionByZero as DecimalDivisionByZero
from decimal import InvalidOperation as DecimalInvalidOperation
from decimal import Overflow as DecimalOverflow

from .parser import CalcError, ResultTooLargeError, _guard_value


class UnitConversionError(CalcError):
    """Raised when a unit conversion cannot be performed."""


# Length base unit: meter (m)
_LENGTH_FACTORS = {
    "m": Decimal("1"),
    "km": Decimal("1000"),
    "cm": Decimal("0.01"),
    "mm": Decimal("0.001"),
    "mile": Decimal("1609.344"),
    "yard": Decimal("0.9144"),
    "foot": Decimal("0.3048"),
    "inch": Decimal("0.0254"),
}

# Mass base unit: kilogram (kg)
_MASS_FACTORS = {
    "kg": Decimal("1"),
    "g": Decimal("0.001"),
    "mg": Decimal("0.000001"),
    "lb": Decimal("0.45359237"),
    "oz": Decimal("0.028349523125"),
    "ton": Decimal("1000"),  # metric ton
}

# Volume base unit: liter (l)
_VOLUME_FACTORS = {
    "l": Decimal("1"),
    "ml": Decimal("0.001"),
    "gallon": Decimal("3.785411784"),
    "quart": Decimal("0.946352946"),
    "pint": Decimal("0.473176473"),
    "cup": Decimal("0.2365882365"),
    "fl_oz": Decimal("0.0295735295625"),
}

_RATIO_CATEGORIES = {
    "length": _LENGTH_FACTORS,
    "mass": _MASS_FACTORS,
    "volume": _VOLUME_FACTORS,
}

_TEMPERATURE_UNITS = frozenset({"celsius", "fahrenheit", "kelvin"})

# Absolute-zero thresholds for each temperature unit.
_ABSOLUTE_ZERO = {
    "celsius": Decimal("-273.15"),
    "fahrenheit": Decimal("-459.67"),
    "kelvin": Decimal("0"),
}


def _resolve_unit(unit: str) -> tuple[str | None, str]:
    """Return (category, canonical_unit) or (None, lowercased_input) if unknown."""
    key = unit.lower()
    for category, factors in _RATIO_CATEGORIES.items():
        if key in factors:
            return category, key
    if key in _TEMPERATURE_UNITS:
        return "temperature", key
    return None, key


def _to_celsius(amount: Decimal, unit: str) -> Decimal:
    if unit == "celsius":
        return amount
    if unit == "fahrenheit":
        return (amount - Decimal("32")) * Decimal("5") / Decimal("9")
    # kelvin
    return amount - Decimal("273.15")


def _from_celsius(celsius: Decimal, unit: str) -> Decimal:
    if unit == "celsius":
        return celsius
    if unit == "fahrenheit":
        return celsius * Decimal("9") / Decimal("5") + Decimal("32")
    # kelvin
    return celsius + Decimal("273.15")


def _convert_ratio(amount: Decimal, from_unit: str, to_unit: str, category: str) -> Decimal:
    factors = _RATIO_CATEGORIES[category]
    base = amount * factors[from_unit]
    return base / factors[to_unit]


def _convert_temperature(amount: Decimal, from_unit: str, to_unit: str) -> Decimal:
    # Validate against the source unit's absolute-zero threshold *before* any
    # affine conversion, so tiny below-threshold values are not rounded away.
    if amount < _ABSOLUTE_ZERO[from_unit]:
        raise UnitConversionError("temperature below absolute zero")
    celsius = _to_celsius(amount, from_unit)
    return _from_celsius(celsius, to_unit)


def convert_unit(amount_str: str, from_unit: str, to_unit: str) -> Decimal:
    """Convert an amount from one physical unit to another.

    Supported categories and units:
      - length (m, km, cm, mm, mile, yard, foot, inch)
      - mass (kg, g, mg, lb, oz, ton)
      - volume (l, ml, gallon, quart, pint, cup, fl_oz)
      - temperature (celsius, fahrenheit, kelvin)

    Unit matching is case-insensitive.  Negative amounts are rejected for
    length, mass, and volume.  Temperatures below absolute zero are rejected.

    Args:
        amount_str: Amount to convert.
        from_unit: Source unit identifier.
        to_unit: Target unit identifier.

    Returns:
        The converted amount as a ``Decimal``.

    Raises:
        UnitConversionError: For unknown units, cross-category conversion,
            negative non-temperature amounts, or temperatures below absolute
            zero.
        ResultTooLargeError: If the result is too large to handle safely.
    """
    from_category, from_canonical = _resolve_unit(from_unit)
    if from_category is None:
        raise UnitConversionError(f"unknown unit: {from_unit}")

    to_category, to_canonical = _resolve_unit(to_unit)
    if to_category is None:
        raise UnitConversionError(f"unknown unit: {to_unit}")

    if from_category != to_category:
        raise UnitConversionError(
            f"cannot convert {from_canonical} to {to_canonical}"
        )

    try:
        amount = Decimal(amount_str)
    except Exception as exc:
        raise UnitConversionError(f"invalid amount: {amount_str!r}") from exc
    amount = _guard_value(amount)

    if from_category != "temperature" and amount < 0:
        raise UnitConversionError(
            f"negative amount not allowed for {from_category}"
        )

    try:
        if from_category == "temperature":
            result = _convert_temperature(amount, from_canonical, to_canonical)
        else:
            result = _convert_ratio(
                amount, from_canonical, to_canonical, from_category
            )
    except (DecimalOverflow, DecimalInvalidOperation, DecimalDivisionByZero) as exc:
        raise ResultTooLargeError("numeric result too large") from exc

    return _guard_value(result)
