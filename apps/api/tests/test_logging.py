"""Tests for sanitized exception logging utilities."""

import io
import logging
import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError

from filament_api.core.logging import format_safe_traceback, log_safe_exception


def test_format_safe_traceback_strips_exception_message_and_params() -> None:
    """Verifies that format_safe_traceback strips SQL and bound parameters from StatementError."""
    secret_canary = "SUPER_SECRET_VALUE_CANARY_12345"
    statement = "INSERT INTO evidence (raw_snippet) VALUES (:snippet)"
    params = {"snippet": secret_canary}

    try:
        raise IntegrityError(statement, params, Exception(f"Database error with {secret_canary}"))
    except Exception as exc:
        formatted = format_safe_traceback(exc)

    assert secret_canary not in formatted
    assert statement not in formatted
    assert "sqlalchemy.exc.IntegrityError" in formatted
    assert "[message and parameters redacted]" in formatted
    assert "File " in formatted
    assert "line " in formatted


def test_format_safe_traceback_preserves_chained_causes() -> None:
    """Verifies that chained causes are preserved with redaction."""
    inner_secret = "INNER_SECRET_PASS_999"
    outer_secret = "OUTER_SECRET_TOKEN_888"

    try:
        try:
            raise ValueError(f"Root failure: {inner_secret}")
        except Exception as inner:
            raise RuntimeError(f"Service error: {outer_secret}") from inner
    except Exception as outer:
        formatted = format_safe_traceback(outer)

    assert inner_secret not in formatted
    assert outer_secret not in formatted
    assert "ValueError" in formatted
    assert "RuntimeError" in formatted
    assert "The above exception was the direct cause of the following exception:" in formatted


def test_format_safe_traceback_handles_no_traceback_gracefully() -> None:
    """Verifies handling of exception without an attached traceback."""
    exc = RuntimeError("Secret in unraised exception")
    formatted = format_safe_traceback(exc)

    assert "Secret in unraised exception" not in formatted
    assert "RuntimeError" in formatted
    assert "<no traceback available>" in formatted


def test_log_safe_exception_emits_error_level_without_exc_info() -> None:
    """Verifies that log_safe_exception logs to error level and sanitizes output."""
    secret_canary = "SENSITIVE_API_KEY_NEVER_LOG"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("test_safe_logger")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    try:
        stmt = "SELECT * FROM agents WHERE api_key_hash = :hash"
        raise StatementError(f"Query error with {secret_canary}", stmt, {"hash": secret_canary}, None)
    except Exception as exc:
        log_safe_exception(logger, "Failed executing agent lookup", exc)

    log_output = stream.getvalue()
    assert secret_canary not in log_output
    assert "Failed executing agent lookup" in log_output
    assert "sqlalchemy.exc.StatementError" in log_output
    assert "File " in log_output

