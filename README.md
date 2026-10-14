# ai-calc

A small, safe command-line calculator designed for AI agents and scripts.

It evaluates arithmetic with exact decimal results, so `0.1 + 0.2` gives `0.3`, not a floating-point approximation. It never calls `eval`, and it rejects inputs that could exhaust memory or CPU.

## Install

Requires Python 3.9 or newer.

```bash
pip install -e .
```

This installs the `ai-calc` command.

## Usage

```bash
ai-calc "0.1 + 0.2"                 # 0.3
ai-calc "sqrt(16) ^ 2"              # 16
ai-calc --fraction "1/3 + 1/6"      # 1/2
ai-calc --date "today + 30"         # date 30 days from today
ai-calc --convert-unit 100 km mile  # unit conversion
ai-calc --compound-interest 10000 5 12 10
ai-calc --convert 100 USD EUR       # live exchange rate
ai-calc --version
```

Run `ai-calc` with no arguments to start an interactive session, where `ans` holds the previous result.

Run `ai-calc --help` for the full syntax and edge cases.

### Expressions

- Operators: `+ - * / ^` and parentheses
- Functions: `sqrt`, `ln`, `log10`, `sin`, `cos`, `tan` (radians)
- Constants: `e`, `pi` (lowercase only)
- Number formats: plain decimals, scientific notation (`1e3`), hex integers (`0xFF`)
- Currency symbols and thousands separators are not accepted. Write `1000`, not `$1,000`.

### Other modes

- `--date`: `YYYY-MM-DD` dates and `today`, with day offsets or day differences. Months and years are not supported because their lengths vary.
- `--fraction`: exact rational arithmetic with `fractions.Fraction`.
- `--convert`: currency conversion using ECB rates from the Frankfurter API, cached for 24 hours. The first lookup for a currency pair needs network access.
- `--compound-interest`: principal, annual rate **as a percent** (`5` means 5%), compounding frequency per year, and years.
- `--convert-unit`: length, mass, volume, and temperature.

## Design goals

- **Exact arithmetic.** Decimal by default, so results match what a person would write by hand.
- **No code execution.** Expressions are parsed by a hand-written recursive-descent parser, so arbitrary input cannot run as code.
- **Resource limits.** Large exponents, very long literals, deeply nested parentheses, and oversized intermediate results are rejected before they are computed.
- **Predictable output for tools.** Errors go to stderr with a non-zero exit code.

## Known limits

- `sin`, `cos`, and `tan` use float precision.
- Currency conversion depends on a third-party API and needs network access for uncached pairs.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e . pytest
.venv/bin/python -m pytest
```

## Licence

Not yet chosen.
