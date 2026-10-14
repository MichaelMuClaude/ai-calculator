# AGENTS.md — guide for AI agents contributing to ai-calc

This file is written for AI coding agents (Claude, Codex, Kimi, GLM, local models, and others) that want to read, test, or change this project. Humans are welcome to read it too; [CONTRIBUTING.md](CONTRIBUTING.md) has the human-facing version of the same rules.

## What this project is

`ai-calc` is a command-line calculator that AI agents call as a tool. Its main promises, in priority order:

1. **Exact results.** Arithmetic uses `decimal.Decimal` (or `fractions.Fraction` in `--fraction` mode), never `float`, unless a function is documented as float-based (`sin`, `cos`, `tan`).
2. **No code execution.** Input is parsed by a hand-written recursive-descent parser in `src/ai_calc/parser.py`. Never add `eval`, `exec`, `ast.literal_eval` on user input, `shell=True`, or string formatting into commands.
3. **Bounded resources.** Every operation that can grow without limit (exponents, literal length, nesting depth, fraction numerators and denominators, intermediate results) must be checked before the expensive step runs, not after.
4. **Predictable CLI behaviour.** Errors go to stderr with exit code 1. Successful results go to stdout. Output must stay stable enough for other tools to parse.

If a change weakens any of these, it should not be merged, however small it looks.

## Layout

```
src/ai_calc/
  cli.py          argument parsing and mode dispatch
  parser.py       tokenizer, recursive-descent parser, Decimal arithmetic, resource guards
  repl.py         interactive mode (ans handling)
  fraction_calc.py  --fraction mode
  date_calc.py    --date mode
  interest.py     --compound-interest mode
  units.py        --convert-unit mode
  exchange.py     --convert mode (network, 24h cache)
tests/            pytest suite; one file per module
SKILL.md          usage notes for agents that call the tool
```

## Setup and checks

Run everything from the repository root. Keep the virtualenv outside any folder synced by a file-sync tool (Dropbox, iCloud, OneDrive); those tools break venv shebangs.

```bash
python3 -m venv ~/.venvs/ai-calc-dev
~/.venvs/ai-calc-dev/bin/pip install -e . pytest
~/.venvs/ai-calc-dev/bin/python -m pytest -q
```

All tests must pass before you open a pull request. Tests must not touch the real network: mock `urlopen` in `exchange.py` as the existing tests do.

## Rules for changes

- **Keep changes small and single-purpose.** One feature or one fix per pull request.
- **Add a test for every behaviour change**, including the failure case. If you fix a bug, add a test that fails before your fix.
- **Adding a new operator, function, or number format touches the tokenizer.** Explain in the pull request how it disambiguates with existing syntax (for example, `e` the constant versus the `e` in `1e3`).
- **Adding a new resource-heavy path requires a guard** before the expensive call. Look at `_check_power_size`, `_guard_value`, and the constants in `parser.py` and reuse them where they fit.
- **Do not change `--help` text silently.** If you add or change a mode, update the help text in `cli.py` and the matching section of `SKILL.md`.
- **Do not add dependencies** unless there is no reasonable standard-library option. The project currently has zero runtime dependencies, and we want to keep it that way.
- **Do not add currency symbols or thousands separators** to accepted input. That is a documented design choice.
- **Keep the Python floor at 3.9.** Do not use syntax or library features newer than that.

## Pull request description

Please include:

- What changed and why, in two or three sentences.
- The test command you ran and its result.
- For parser or arithmetic changes: the inputs you tried, including adversarial ones (very large exponents, very long literals, deep nesting), and what happened.
- A line stating that the change was produced with AI assistance, and which tool and model you used. Disclosure is expected and does not count against a change.

## Security

Do not report vulnerabilities in a public issue. Open a private security advisory on GitHub for this repository instead. Any input that can cause a crash with a traceback, a hang, or unbounded memory use counts as a bug worth reporting.

## Good first tasks for agents

- Add a test for an input class that is not yet covered (see `tests/test_parser.py` for the style).
- Improve an error message so it names the offending token.
- Review an existing guard and write a test that tries to bypass it.
- Check that `--help` and `SKILL.md` agree with each other.
