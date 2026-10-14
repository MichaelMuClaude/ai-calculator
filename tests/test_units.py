from decimal import Decimal

import pytest

from ai_calc.parser import CalcError, ResultTooLargeError
from ai_calc.units import UnitConversionError, convert_unit


# Correctness tests per category


def test_length_mile_to_meter():
    assert convert_unit("1", "mile", "m") == Decimal("1609.344")


def test_length_kilometer_to_meter():
    assert convert_unit("1", "km", "m") == 1000


def test_length_inch_to_centimeter():
    assert convert_unit("1", "inch", "cm") == Decimal("2.54")


def test_mass_pound_to_kilogram():
    assert convert_unit("1", "lb", "kg") == Decimal("0.45359237")


def test_mass_ton_to_kilogram():
    assert convert_unit("1", "ton", "kg") == 1000


def test_volume_gallon_to_liter():
    assert convert_unit("1", "gallon", "l") == Decimal("3.785411784")


def test_volume_cup_to_milliliter():
    assert convert_unit("1", "cup", "ml") == Decimal("236.5882365")


def test_temperature_celsius_to_fahrenheit():
    assert convert_unit("0", "celsius", "fahrenheit") == 32
    assert convert_unit("100", "celsius", "fahrenheit") == 212


def test_temperature_celsius_to_kelvin():
    assert convert_unit("0", "celsius", "kelvin") == Decimal("273.15")


def test_temperature_fahrenheit_to_celsius():
    assert convert_unit("32", "fahrenheit", "celsius") == 0


def test_temperature_kelvin_to_celsius():
    assert convert_unit("273.15", "kelvin", "celsius") == 0


def test_temperature_minus_40_is_same():
    assert convert_unit("-40", "celsius", "fahrenheit") == -40


# Round-trip conversions


def test_length_round_trip():
    original = Decimal("5")
    intermediate = convert_unit(str(original), "km", "mile")
    back = convert_unit(str(intermediate), "mile", "km")
    assert back == original


def test_mass_round_trip():
    original = Decimal("2.5")
    intermediate = convert_unit(str(original), "kg", "lb")
    back = convert_unit(str(intermediate), "lb", "kg")
    assert back == original


def test_volume_round_trip():
    original = Decimal("3")
    intermediate = convert_unit(str(original), "l", "gallon")
    back = convert_unit(str(intermediate), "gallon", "l")
    assert back == original


def test_temperature_round_trip():
    original = Decimal("100")
    intermediate = convert_unit(str(original), "celsius", "fahrenheit")
    back = convert_unit(str(intermediate), "fahrenheit", "celsius")
    assert back == original


# Rejection tests


def test_cross_category_rejected():
    with pytest.raises(UnitConversionError):
        convert_unit("1", "km", "kg")


def test_unknown_unit_rejected():
    with pytest.raises(UnitConversionError):
        convert_unit("1", "foo", "m")
    with pytest.raises(UnitConversionError):
        convert_unit("1", "m", "foo")


def test_negative_amount_rejected_for_non_temperature():
    with pytest.raises(UnitConversionError):
        convert_unit("-1", "m", "km")
    with pytest.raises(UnitConversionError):
        convert_unit("-1", "kg", "g")
    with pytest.raises(UnitConversionError):
        convert_unit("-1", "l", "ml")


def test_negative_temperature_allowed():
    # Negative temperatures are fine as long as they are above absolute zero.
    assert convert_unit("-10", "celsius", "fahrenheit") == 14


def test_below_absolute_zero_rejected():
    with pytest.raises(UnitConversionError):
        convert_unit("-300", "celsius", "kelvin")
    with pytest.raises(UnitConversionError):
        convert_unit("-500", "fahrenheit", "celsius")
    with pytest.raises(UnitConversionError):
        convert_unit("-1", "kelvin", "celsius")


def test_tiny_below_absolute_zero_rejected():
    # Regression: validation must happen in the source unit, before affine
    # conversion can round away the tiny violation.
    with pytest.raises(UnitConversionError):
        convert_unit("-0.000000000000000000000000001", "kelvin", "celsius")
    with pytest.raises(UnitConversionError):
        convert_unit("-273.150000000000000000000000001", "celsius", "kelvin")
    with pytest.raises(UnitConversionError):
        convert_unit("-459.670000000000000000000000001", "fahrenheit", "celsius")


def test_absolute_zero_boundary_allowed():
    assert convert_unit("-273.15", "celsius", "kelvin") == 0
    assert convert_unit("-459.67", "fahrenheit", "celsius") == Decimal("-273.15")
    assert convert_unit("0", "kelvin", "celsius") == Decimal("-273.15")


def test_case_insensitive_units():
    assert convert_unit("1", "MILE", "m") == Decimal("1609.344")
    assert convert_unit("1", "Celsius", "KELVIN") == Decimal("274.15")


def test_invalid_amount_rejected():
    with pytest.raises(UnitConversionError):
        convert_unit("abc", "m", "km")


def test_unit_conversion_error_is_calc_error():
    assert issubclass(UnitConversionError, CalcError)


def test_oversized_amount_rejected():
    with pytest.raises(ResultTooLargeError):
        convert_unit("9" * 5000, "m", "km")
