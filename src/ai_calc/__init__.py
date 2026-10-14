"""ai-calc: a safe command-line calculator for arithmetic expressions."""

from .parser import calculate, CalcError

__version__ = "0.1.0"

__all__ = ["calculate", "CalcError", "__version__"]
