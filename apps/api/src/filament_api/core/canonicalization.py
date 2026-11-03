"""Path canonicalization utilities adhering strictly to Step 21C invariants."""

class PathValidationError(ValueError):
    """Raised when environment path validation or canonicalization fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def canonicalize_path(raw: str, allow_root_marker: bool = False) -> str:
    """Canonicalize a filesystem path according to Step 21C strict path rules.

    Rules:
    1. Reject leading/trailing whitespace outright (no silent trimming).
    2. Reject empty path.
    3. Allow '.' exclusively when allow_root_marker=True (e.g., scanned_roots).
    4. Reject absolute paths (POSIX / or Windows C:).
    5. Normalize backslashes to POSIX forward slashes.
    6. Reject trailing slashes unless allow_root_marker=True.
       NOTE: file_hash and lockfile_hash conditions operate strictly on files, not directories.
    7. Reject path traversal ('..') segments.
    8. Filter clean segments and ensure path does not resolve to empty root.
    """
    if not isinstance(raw, str):
        raise PathValidationError(f"Path must be a string, got {type(raw).__name__}.")

    # 1. Reject leading or trailing whitespace
    if raw != raw.strip():
        raise PathValidationError(f"Path must not contain leading or trailing whitespace: '{raw}'")

    # 2. Reject empty path
    if not raw:
        raise PathValidationError("Path cannot be empty.")

    # 3. Allow '.' exclusively for scan scope roots
    if raw == ".":
        if allow_root_marker:
            return "."
        raise PathValidationError("'.' is a repository root marker and cannot be a condition target.")

    # 4. Reject absolute paths
    if raw.startswith(("/", "\\")) or (len(raw) > 1 and raw[1] == ":" and raw[0].isalpha()):
        raise PathValidationError(f"Absolute paths are forbidden: '{raw}'")

    # 5. Normalize backslashes to POSIX forward slashes
    posix = raw.replace("\\", "/")

    # 6. Reject trailing slashes for file targets
    if posix.endswith("/") and not allow_root_marker:
        raise PathValidationError(f"Target file path must not end with a trailing slash: '{raw}'")

    # 7. Check for traversal segments
    segments = posix.rstrip("/").split("/")
    if ".." in segments:
        raise PathValidationError(f"Path traversal ('..') is forbidden: '{raw}'")

    # 8. Filter and construct clean path
    clean_segments = [s for s in segments if s and s != "."]
    if not clean_segments:
        raise PathValidationError(f"Path resolves to empty root: '{raw}'")

    return "/".join(clean_segments)


def validate_package_identifier(raw: str) -> str:
    """Validate and canonicalize a package identifier in '<ecosystem>:<package-name>' format.

    Rules:
    - Must not contain leading or trailing whitespace.
    - Must contain at least one ':' separating ecosystem and package name.
    - Ecosystem must be non-empty lowercase alphanumeric/hyphen/underscore (e.g. pypi, npm, cargo, go).
    - Package name must be non-empty.
    - Returns normalized '<ecosystem>:<package-name>'.
    """
    if not isinstance(raw, str):
        raise PathValidationError(f"Package identifier must be a string, got {type(raw).__name__}.")
    if raw != raw.strip():
        raise PathValidationError(f"Package identifier must not contain leading or trailing whitespace: '{raw}'")
    if not raw:
        raise PathValidationError("Package identifier cannot be empty.")
    if ":" not in raw:
        raise PathValidationError(
            f"Package identifier '{raw}' must include an ecosystem namespace prefix (e.g. 'pypi:flask', 'npm:react')."
        )
    parts = raw.split(":", 1)
    ecosystem, name = parts[0], parts[1]
    if not ecosystem or not ecosystem.strip():
        raise PathValidationError(f"Package identifier '{raw}' has an empty ecosystem prefix.")
    if not name or not name.strip():
        raise PathValidationError(f"Package identifier '{raw}' has an empty package name.")

    eco_norm = ecosystem.strip().lower()
    if not all(c.isalnum() or c in ("-", "_") for c in eco_norm):
        raise PathValidationError(
            f"Invalid ecosystem prefix '{ecosystem}' in package identifier '{raw}'. "
            "Must be alphanumeric with optional hyphens/underscores."
        )

    return f"{eco_norm}:{name.strip()}"

