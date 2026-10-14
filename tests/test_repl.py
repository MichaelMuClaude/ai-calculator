import pytest

from ai_calc.repl import run_repl


class _InputSequence:
    """Callable that returns preset lines and finally raises EOFError."""

    def __init__(self, lines):
        self._lines = list(lines)
        self._index = 0

    def __call__(self) -> str:
        if self._index >= len(self._lines):
            raise EOFError
        line = self._lines[self._index]
        self._index += 1
        return line


class _OutputCollector:
    """Callable that records every string passed to it."""

    def __init__(self):
        self.lines = []

    def __call__(self, text: str) -> None:
        self.lines.append(text)


@pytest.fixture
def make_repl():
    """Return a helper that builds injected input/output and runs run_repl."""

    def _run(lines):
        inp = _InputSequence(lines)
        out = _OutputCollector()
        code = run_repl(inp, out)
        return code, out.lines

    return _run


def test_repl_ans_references_previous_result_exactly(make_repl):
    code, lines = make_repl(["0.1 + 0.2", "ans * 3", "exit"])
    assert code == 0
    assert "0.3" in lines
    assert "0.9" in lines


def test_repl_ans_before_defined_is_clear_error(make_repl):
    code, lines = make_repl(["ans + 1", "exit"])
    assert code == 0
    assert any("ans is not defined yet" in line for line in lines)


def test_repl_error_preserves_ans(make_repl):
    code, lines = make_repl(["2 + 2", "1 / 0", "ans + 1", "exit"])
    assert code == 0
    # First successful result is 4, division-by-zero error should leave ans as 4.
    assert "4" in lines
    assert any("division by zero" in line for line in lines)
    assert "5" in lines


def test_repl_empty_lines_are_ignored(make_repl):
    code, lines = make_repl(["", "   ", "1 + 1", "exit"])
    assert code == 0
    assert "2" in lines
    assert not any(line.startswith("Error:") for line in lines)


@pytest.mark.parametrize("command", ["exit", "EXIT", "quit", "Quit", "eXiT"])
def test_repl_exit_and_quit_case_insensitive(command):
    inp = _InputSequence([command])
    out = _OutputCollector()
    assert run_repl(inp, out) == 0


def test_repl_eof_exits_cleanly():
    def eof():
        raise EOFError

    out = _OutputCollector()
    assert run_repl(eof, out) == 0


def test_repl_keyboard_interrupt_does_not_exit():
    calls = [0]

    def interrupted():
        calls[0] += 1
        if calls[0] == 1:
            raise KeyboardInterrupt
        return "exit"

    out = _OutputCollector()
    code = run_repl(interrupted, out)
    assert code == 0
    assert any("exit/quit" in line or "Ctrl+D" in line for line in out.lines)


def test_repl_calc_error_does_not_crash_repl(make_repl):
    code, lines = make_repl(["1 + * 2", "exit"])
    assert code == 0
    assert any(line.startswith("Error:") for line in lines)


def test_repl_ans_negative_value_is_parenthesized(make_repl):
    # Regression: ans must be parenthesized so -1 ^ 2 is parsed as (-1)^2.
    code, lines = make_repl(["-1", "ans^2", "exit"])
    assert code == 0
    assert "1" in lines
    assert "-1" in lines


def test_repl_ans_decimal_scientific_notation_is_rereadable(make_repl):
    # Regression: Decimal's scientific notation (E+400) is not tokenized,
    # so ans must be substituted in fixed-point notation.
    code, lines = make_repl(["10.0^400", "ans+1", "exit"])
    assert code == 0
    # Both the original result and the fixed-point re-read result appear.
    assert any("E+400" in line for line in lines)
    assert any(line.startswith("1000") and line.endswith("1") for line in lines)


def test_repl_huge_integer_error_does_not_crash_repl(make_repl):
    # Regression: a borderline oversized integer must raise CalcError,
    # not an unhandled ValueError that exits the REPL.
    code, lines = make_repl(["10^4299", "ans*10", "exit"])
    assert code == 0
    assert any("result too large to print" in line for line in lines)

