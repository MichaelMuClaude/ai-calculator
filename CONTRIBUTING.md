# Contributing to ai-calc

Thanks for helping. Both humans and AI agents can contribute. The detailed guide for agents is in [AGENTS.md](AGENTS.md); the short version is below.

## Ground rules

- Exact arithmetic, no `eval`, bounded resources, and stable CLI output are the core promises. See [AGENTS.md](AGENTS.md#what-this-project-is).
- Keep changes small. One feature or fix per pull request.
- Every behaviour change needs a test, including the failure case.
- Run the test suite before you open a pull request.

## Running the tests

```bash
python3 -m venv ~/.venvs/ai-calc-dev
~/.venvs/ai-calc-dev/bin/pip install -e . pytest
~/.venvs/ai-calc-dev/bin/python -m pytest -q
```

Continuous integration runs the same suite on Python 3.9 and 3.13 for every pull request.

## Opening a pull request

1. Fork the repository and create a branch with a descriptive name, such as `fix/power-guard-message` or `feat/cube-root`.
2. Make your change with tests.
3. In the pull request description, say what changed, why, and which tests you ran.
4. If an AI agent wrote or helped write the change, say so in the description and name the tool and model.

## Reporting bugs

Open an issue with the exact command, the output you got, and the output you expected. If the bug is a crash, a hang, or unbounded resource use, use a private security advisory instead (see [AGENTS.md](AGENTS.md#security)).

## Licence

By contributing, you agree that your contribution is released under the MIT licence in [LICENSE](LICENSE).
