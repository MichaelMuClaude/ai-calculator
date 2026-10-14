"""Command-line entry point for ``ai-calc``."""

from __future__ import annotations

import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import __version__
from .date_calc import calculate_date
from .exchange import convert
from .fraction_calc import calculate_fraction, format_fraction
from .interest import calculate_compound_interest
from .parser import calculate, CalcError, ResultTooLargeError
from .repl import run_repl
from .units import convert_unit


def _print_usage() -> int:
    print("Usage: ai-calc <expression>", file=sys.stderr)
    print("       ai-calc --date <expression>", file=sys.stderr)
    print("       ai-calc --fraction <expression>", file=sys.stderr)
    print("       ai-calc --convert <amount> <FROM> <TO>", file=sys.stderr)
    print(
        "       ai-calc --compound-interest <principal> <rate_percent> "
        "<times_per_year> <years>",
        file=sys.stderr,
    )
    print(
        "       ai-calc --convert-unit <amount> <FROM_UNIT> <TO_UNIT>",
        file=sys.stderr,
    )
    print("Try 'ai-calc --help' for more information.", file=sys.stderr)
    return 2


def _format_currency(value: Decimal) -> str:
    """Format a Decimal amount as currency with two decimal places, rounding half up."""
    try:
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ResultTooLargeError("numeric result too large to print") from exc


def _print_help() -> None:
    print("Usage: ai-calc <expression>")
    print("       ai-calc --date <expression>")
    print("       ai-calc --fraction <expression>")
    print("       ai-calc --convert <amount> <FROM> <TO>")
    print(
        "       ai-calc --compound-interest <principal> <rate_percent> "
        "<times_per_year> <years>"
    )
    print("       ai-calc --convert-unit <amount> <FROM_UNIT> <TO_UNIT>")
    print("       ai-calc --version")
    print()
    print("Run without arguments to start an interactive REPL.")
    print()
    print("Evaluate a safe arithmetic expression.")
    print()
    print("Supported operators: +, -, *, /, ^, parentheses")
    print("Supported functions: sqrt, ln, log10, sin, cos, tan")
    print("Supported constants: e, pi (lowercase only)")
    print("Supported number formats: scientific notation (1e3, 1.5e-10),")
    print("                          hex integers (0x10, 0xFF)")
    print("Note: plain decimal numbers only -- no currency symbols ($, £),")
    print("      no thousands separators (write 1000, not 1,000 or $1,000).")
    print("Note: sin, cos, and tan use standard float precision (radians),")
    print("      not exact Decimal arithmetic.")
    print()
    print("Date mode (--date):")
    print("  Supports: today keyword, YYYY-MM-DD literals,")
    print("            date + days, date - days, date - date")
    print("  Returns:  YYYY-MM-DD for date +/- days,")
    print("            signed day count for date - date")
    print("  Does NOT support: months/years (ambiguous lengths).")
    print("  <expression> arguments (day offsets) are plain integers, e.g.")
    print("    '2026-01-01 + 30' or 'today - 2025-01-01'.")
    print()
    print("Exact fraction mode (--fraction):")
    print("  Uses fractions.Fraction for exact rational arithmetic.")
    print("  Supports: +, -, *, /, ^ (integer exponents only), parentheses,")
    print("            unary +/-, and decimal literals (e.g. 0.5 -> 1/2).")
    print("  Does NOT support: built-in functions, non-integer exponents,")
    print("                    REPL ans, --convert, --compound-interest,")
    print("                    or --convert-unit.")
    print()
    print("Currency conversion (--convert <amount> <FROM> <TO>):")
    print("  amount: plain decimal number, e.g. 100 or 99.95")
    print("          (no currency symbols, no thousands separators;")
    print("          negative amounts are accepted).")
    print("  FROM/TO: 3-letter ISO 4217 currency code, UPPERCASE only,")
    print("           e.g. USD, EUR, AUD, GBP, JPY (lowercase is rejected).")
    print("  Rates are fetched live (ECB, via Frankfurter) and cached 24h;")
    print("  requires network access on first lookup for a given pair.")
    print()
    print("Compound interest (--compound-interest <principal> <rate_percent>")
    print("                    <times_per_year> <years>):")
    print("  principal:      positive decimal amount, no currency symbol,")
    print("                  e.g. 10000 or 10000.50")
    print("  rate_percent:   annual rate AS A PERCENT, e.g. 5 means 5%")
    print("                  (NOT 0.05). May be negative to model")
    print("                  depreciation, as long as (1 + rate/n) stays")
    print("                  positive.")
    print("  times_per_year: positive integer compounding frequency,")
    print("                  e.g. 1 = annually, 4 = quarterly, 12 = monthly,")
    print("                  365 = daily.")
    print("  years:          non-negative number of years; decimals are")
    print("                  allowed, e.g. 2.5 for two and a half years.")
    print()
    print("Unit conversion (--convert-unit <amount> <FROM_UNIT> <TO_UNIT>):")
    print("  amount: plain decimal number. Negative values are rejected for")
    print("          length/mass/volume but allowed for temperature (down to")
    print("          absolute zero).")
    print("  FROM_UNIT/TO_UNIT: unit name, case-insensitive, both units must")
    print("                     be in the same category:")
    print("    length:      m, km, cm, mm, mile, yard, foot, inch")
    print("    mass:        kg, g, mg, lb, oz, ton (metric ton)")
    print("    volume:      l, ml, gallon, quart, pint, cup, fl_oz")
    print("    temperature: celsius, fahrenheit, kelvin")
    print()
    print("REPL supports: arithmetic expressions, functions, and 'ans'.")
    print("REPL does NOT support: --convert, --compound-interest,")
    print("                       --convert-unit (use them as shell args).")


def main(argv: list[str] | None = None) -> int:
    """Run the ``ai-calc`` command.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` on success, ``1`` on a calculation error, ``2`` on usage error.
    """
    # Guard against UnicodeEncodeError when stdout is redirected under a
    # non-UTF-8 locale (e.g. LC_ALL=C in cron jobs or containers).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] in ("--help", "-h"):
        _print_help()
        return 0

    if argv and argv[0] == "--version":
        print(f"ai-calc {__version__}")
        return 0

    if argv and argv[0] == "--fraction":
        if len(argv) != 2:
            print(
                "Usage: ai-calc --fraction <expression>", file=sys.stderr
            )
            return 2
        expression = argv[1]
        try:
            result = calculate_fraction(expression)
        except CalcError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(format_fraction(result))
        return 0

    if argv and argv[0] == "--convert-unit":
        if len(argv) != 4:
            print(
                "Usage: ai-calc --convert-unit <amount> <FROM_UNIT> <TO_UNIT>",
                file=sys.stderr,
            )
            print(
                "       units are case-insensitive, e.g. km, mile, kg, lb, "
                "l, gallon, celsius",
                file=sys.stderr,
            )
            return 2
        _, amount, from_unit, to_unit = argv
        try:
            result = convert_unit(amount, from_unit, to_unit)
        except CalcError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(result)
        return 0

    if argv and argv[0] == "--convert":
        if len(argv) != 4:
            print(
                "Usage: ai-calc --convert <amount> <FROM> <TO>", file=sys.stderr
            )
            print(
                "       FROM/TO are 3-letter uppercase ISO currency codes, "
                "e.g. USD EUR AUD",
                file=sys.stderr,
            )
            return 2
        _, amount, from_code, to_code = argv
        try:
            result = convert(amount, from_code, to_code)
        except CalcError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(result)
        return 0

    if argv and argv[0] == "--compound-interest":
        if len(argv) != 5:
            print(
                "Usage: ai-calc --compound-interest <principal> <rate_percent> "
                "<times_per_year> <years>",
                file=sys.stderr,
            )
            print(
                "       rate_percent is an annual percentage (e.g. 5 for 5%)",
                file=sys.stderr,
            )
            return 2
        _, principal, rate_percent, times_per_year, years = argv
        try:
            result = calculate_compound_interest(
                principal, rate_percent, times_per_year, years
            )
            print(_format_currency(result))
        except CalcError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if argv and argv[0] == "--date":
        if len(argv) != 2:
            print("Usage: ai-calc --date <expression>", file=sys.stderr)
            return 2
        expression = argv[1]
        try:
            result = calculate_date(expression)
        except CalcError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(result)
        return 0

    if len(argv) == 0:
        return run_repl()

    if len(argv) == 1 and re.match(r"^--[a-zA-Z]", argv[0]):
        print(f"Error: unknown option: '{argv[0]}'", file=sys.stderr)
        _print_usage()
        return 2

    if len(argv) != 1:
        return _print_usage()

    expression = argv[0]
    try:
        result = calculate(expression)
    except CalcError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
