"""Sanitized exception logging utilities.

Preserves exception class and traceback frames (file, line, function)
while strictly stripping exception messages, bound SQL parameters,
local variables, and sensitive payloads to prevent secret leakage in logs.
"""

from collections.abc import Sequence
import logging
import traceback


def format_safe_traceback(exc: BaseException) -> str:
    """Format traceback call stack and exception type without exception messages.

    Traverses chained causes and contexts, formatting file path, line number,
    and function names while redacting all exception message strings and SQL parameters.
    """
    chain: list[BaseException] = []
    curr: BaseException | None = exc
    visited: set[int] = set()

    while curr is not None and id(curr) not in visited:
        visited.add(id(curr))
        chain.append(curr)
        curr = curr.__cause__ or (curr.__context__ if not curr.__suppress_context__ else None)

    chain.reverse()
    parts: list[str] = []

    for i, e in enumerate(chain):
        lines: list[str] = []
        if i > 0:
            lines.append("\nThe above exception was the direct cause of the following exception:\n\n")

        lines.append("Traceback (most recent call last):\n")
        tb: Sequence[traceback.FrameSummary] = (
            traceback.extract_tb(e.__traceback__) if e.__traceback__ is not None else []
        )
        if not tb:
            lines.append("  <no traceback available>\n")
        else:
            for frame in tb:
                lines.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n')
                if frame.line:
                    lines.append(f"    {frame.line}\n")

        e_type = type(e)
        qualname = (
            f"{e_type.__module__}.{e_type.__qualname__}"
            if e_type.__module__ != "builtins"
            else e_type.__qualname__
        )
        lines.append(f"{qualname}: [message and parameters redacted]")
        parts.append("".join(lines))

    return "".join(parts)


def log_safe_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    """Log an error message with a sanitized traceback that excludes sensitive messages and parameters."""
    safe_tb = format_safe_traceback(exc)
    logger.error("%s\n%s", message, safe_tb)

