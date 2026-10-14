"""Interactive REPL for ``ai-calc``.

This module implements a read-eval-print loop. In REPL mode, only plain
arithmetic expressions and the built-in functions ``sqrt``/``ln``/``log10``/
``sin``/``cos``/``tan`` are supported.

The subcommands ``--convert``, ``--compound-interest``, and
``--convert-unit`` are **not** available inside the REPL; invoke them
directly from the shell as separate ``ai-calc`` command-line arguments.

The special variable ``ans`` holds the result of the last successful
evaluation and can be used in subsequent expressions.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Callable

from .parser import CalcError, calculate

_PROMPT = "ai-calc> "
_ANS_RE = re.compile(r"\bans\b")
_EXIT_WORDS = frozenset(("exit", "quit"))


def run_repl(
    input_func: Callable[[], str] = input,
    output_func: Callable[[str], None] = print,
) -> int:
    """Run the interactive ``ai-calc`` REPL.

    Args:
        input_func: Callable returning the next input line. The default is
            the built-in ``input``. ``EOFError`` is treated as the user
            pressing Ctrl+D and causes a clean exit.
        output_func: Callable accepting a single string to display. The
            default is the built-in ``print``.

    Returns:
        ``0`` on a clean exit (``exit``/``quit`` or Ctrl+D).
    """
    last_result: object = None

    while True:
        try:
            output_func(_PROMPT)
            try:
                line = input_func()
            except EOFError:
                output_func("")
                return 0

            stripped = line.strip()
            if not stripped:
                continue

            if stripped.lower() in _EXIT_WORDS:
                return 0

            expression = stripped
            if _ANS_RE.search(expression):
                if last_result is None:
                    output_func("Error: ans is not defined yet")
                    continue
                # Preserve the exact value in fixed-point (non-scientific)
                # notation so the parser can re-read it, and wrap it in
                # parentheses so negative values keep their meaning.
                ans_value = Decimal(str(last_result))
                expression = _ANS_RE.sub(f"({format(ans_value, 'f')})", expression)

            try:
                result = calculate(expression)
            except CalcError as exc:
                output_func(f"Error: {exc}")
                continue
            except Exception as exc:
                output_func("Error: internal error")
                continue

            last_result = result
            output_func(str(result))

        except KeyboardInterrupt:
            output_func("")
            output_func("(使用 exit/quit 或 Ctrl+D 退出)")
            continue
