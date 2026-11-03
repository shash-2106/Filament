"""Security and cryptographic primitives for credential hashing and verification."""

import hashlib
import hmac

# Maximum permissible length for an incoming API bearer token (prevents hash DoS)
MAX_TOKEN_LENGTH = 512


def hash_api_key(token: str) -> str:
    """Compute the SHA-256 hexadecimal digest of a raw API key.

    Raw API keys are never stored or logged in Filament. Only the resulting
    64-character lowercase hex digest is persisted in the database.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_api_key_hash(token: str, expected_hash: str) -> bool:
    """Verify a raw API key against an expected SHA-256 hash in constant time."""
    computed_hash = hash_api_key(token)
    return hmac.compare_digest(computed_hash.lower(), expected_hash.lower())

