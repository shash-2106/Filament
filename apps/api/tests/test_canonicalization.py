"""Unit tests for Step 21C path canonicalization specification."""

import pytest

from filament_api.core.canonicalization import (
    PathValidationError,
    canonicalize_path,
    validate_package_identifier,
)


def test_canonicalize_path_valid_relative_paths() -> None:
    """Verifies that clean relative paths are preserved or normalized."""
    assert canonicalize_path("src/main.py") == "src/main.py"
    assert canonicalize_path("config/redis.conf") == "config/redis.conf"
    assert canonicalize_path("src\\sub\\file.txt") == "src/sub/file.txt"
    assert canonicalize_path("a/b/c/d.json") == "a/b/c/d.json"


def test_canonicalize_path_rejects_leading_trailing_whitespace() -> None:
    """Verifies that leading or trailing whitespace is rejected outright without silent trimming."""
    with pytest.raises(PathValidationError, match="leading or trailing whitespace"):
        canonicalize_path(" src/main.py")

    with pytest.raises(PathValidationError, match="leading or trailing whitespace"):
        canonicalize_path("src/main.py ")

    with pytest.raises(PathValidationError, match="leading or trailing whitespace"):
        canonicalize_path("\tsrc/main.py")


def test_canonicalize_path_rejects_empty() -> None:
    """Verifies that empty paths are rejected."""
    with pytest.raises(PathValidationError, match="Path cannot be empty"):
        canonicalize_path("")


def test_canonicalize_path_root_marker() -> None:
    """Verifies that '.' is rejected for file targets but allowed for scan scope roots."""
    # Forbidden for condition targets
    with pytest.raises(PathValidationError, match="repository root marker and cannot be a condition target"):
        canonicalize_path(".", allow_root_marker=False)

    # Allowed for scan scope roots
    assert canonicalize_path(".", allow_root_marker=True) == "."


def test_canonicalize_path_rejects_absolute_paths() -> None:
    """Verifies that POSIX and Windows absolute paths are forbidden."""
    with pytest.raises(PathValidationError, match="Absolute paths are forbidden"):
        canonicalize_path("/etc/passwd")

    with pytest.raises(PathValidationError, match="Absolute paths are forbidden"):
        canonicalize_path("\\Windows\\System32")

    with pytest.raises(PathValidationError, match="Absolute paths are forbidden"):
        canonicalize_path("C:/Users/test/file.txt")


def test_canonicalize_path_rejects_trailing_slash_for_files() -> None:
    """Verifies that trailing slash is forbidden for file condition targets."""
    with pytest.raises(PathValidationError, match="must not end with a trailing slash"):
        canonicalize_path("src/main.py/", allow_root_marker=False)

    # Allowed when allow_root_marker=True (e.g. directory roots)
    assert canonicalize_path("src/", allow_root_marker=True) == "src"


def test_canonicalize_path_rejects_traversal() -> None:
    """Verifies that '..' segments are strictly rejected."""
    with pytest.raises(PathValidationError, match="Path traversal"):
        canonicalize_path("../secret.env")

    with pytest.raises(PathValidationError, match="Path traversal"):
        canonicalize_path("src/../../secret.env")

    with pytest.raises(PathValidationError, match="Path traversal"):
        canonicalize_path("src/../main.py")


def test_canonicalize_path_rejects_empty_segments_resolving_to_nothing() -> None:
    """Verifies that paths resolving to empty root are rejected."""
    with pytest.raises(PathValidationError, match="resolves to empty root"):
        canonicalize_path("././.")


def test_validate_package_identifier_valid() -> None:
    """Verifies valid package identifiers across diverse package ecosystems."""
    assert validate_package_identifier("pypi:flask") == "pypi:flask"
    assert validate_package_identifier("npm:react") == "npm:react"
    assert validate_package_identifier("npm:@scope/package") == "npm:@scope/package"
    assert validate_package_identifier("cargo:serde") == "cargo:serde"
    assert validate_package_identifier("go:github.com/gin-gonic/gin") == "go:github.com/gin-gonic/gin"
    assert validate_package_identifier("PyPI:Flask") == "pypi:Flask"


def test_validate_package_identifier_invalid() -> None:
    """Verifies invalid package identifiers are rejected with descriptive errors."""
    with pytest.raises(PathValidationError, match="must include an ecosystem namespace prefix"):
        validate_package_identifier("flask")

    with pytest.raises(PathValidationError, match="leading or trailing whitespace"):
        validate_package_identifier(" pypi:flask")

    with pytest.raises(PathValidationError, match="leading or trailing whitespace"):
        validate_package_identifier("pypi:flask ")

    with pytest.raises(PathValidationError, match="cannot be empty"):
        validate_package_identifier("")

    with pytest.raises(PathValidationError, match="empty ecosystem prefix"):
        validate_package_identifier(":flask")

    with pytest.raises(PathValidationError, match="empty package name"):
        validate_package_identifier("pypi:")

    with pytest.raises(PathValidationError, match="Invalid ecosystem prefix"):
        validate_package_identifier("pypi!:flask")

    with pytest.raises(PathValidationError, match="must be a string"):
        validate_package_identifier(123)  # type: ignore[arg-type]

