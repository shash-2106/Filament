"""Re-export canonicalization utilities from filament_api.core."""

from filament_api.core.canonicalization import (
    canonicalize_path,
    validate_package_identifier,
)

__all__ = ["canonicalize_path", "validate_package_identifier"]
