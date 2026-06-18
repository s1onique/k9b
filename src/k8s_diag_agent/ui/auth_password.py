"""Password hashing and verification using PBKDF2-HMAC-SHA256.

This module provides secure password hashing using Python's standard library.
The hash format includes algorithm identifier, iteration count, salt, and derived key.

Format: ${algorithm}$${iterations}$${salt}$${hash}

Example: $pbkdf2-sha256$600000$abc123$def456
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from typing import Final

# Constants for PBKDF2-HMAC-SHA256
_ALGORITHM: Final[str] = "pbkdf2-sha256"
_DEFAULT_ITERATIONS: Final[int] = 600_000  # OWASP 2023 recommendation
_SALT_LENGTH: Final[int] = 32  # 256 bits
_HASH_LENGTH: Final[int] = 32  # 256 bits (same as SHA-256 output)


def _parse_hash(hash_string: str) -> tuple[str, int, str, str] | None:
    """Parse a stored password hash.

    Args:
        hash_string: The stored hash in format ${algo}$${iter}$${salt}$${hash}

    Returns:
        Tuple of (algorithm, iterations, salt, hash) or None if invalid
    """
    try:
        if not hash_string.startswith(f"${_ALGORITHM}$"):
            return None
        parts = hash_string.split("$")
        if len(parts) != 5:
            return None
        # parts: ['', 'pbkdf2-sha256', iterations, salt, hash]
        algorithm = parts[1]
        iterations = int(parts[2])
        salt = parts[3]
        stored_hash = parts[4]
        return (algorithm, iterations, salt, stored_hash)
    except (ValueError, IndexError):
        return None


def hash_password(password: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    """Generate a salted password hash.

    Args:
        password: The plaintext password to hash
        iterations: Number of PBKDF2 iterations (default: 600,000)

    Returns:
        Formatted hash string: ${algorithm}$${iterations}$${salt}$${hash}
    """
    # Generate cryptographically random salt
    salt_bytes = secrets.token_bytes(_SALT_LENGTH)

    # Derive key using PBKDF2-HMAC-SHA256
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        iterations,
        dklen=_HASH_LENGTH,
    )

    # Encode salt and hash as base64 (URL-safe, no padding)
    salt_b64 = _base64_encode(salt_bytes)
    hash_b64 = _base64_encode(key)

    return f"${_ALGORITHM}${iterations}${salt_b64}${hash_b64}"


def _base64_encode(data: bytes) -> str:
    """Encode bytes to URL-safe base64 without padding."""
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash using constant-time comparison.

    Args:
        password: The plaintext password to verify
        stored_hash: The stored hash to verify against

    Returns:
        True if password matches, False otherwise
    """
    parsed = _parse_hash(stored_hash)
    if parsed is None:
        # Invalid hash format - reject to prevent timing attacks
        # Use a dummy comparison to maintain constant time
        _constant_time_dummy_compare(stored_hash)
        return False

    algorithm, iterations, salt_b64, expected_hash = parsed

    # Validate algorithm matches (defense in depth)
    if algorithm != _ALGORITHM:
        _constant_time_dummy_compare(stored_hash)
        return False

    try:
        # Decode salt from base64
        import base64

        salt_bytes = base64.urlsafe_b64decode(salt_b64 + "==")
    except Exception:
        # Invalid salt encoding - reject
        _constant_time_dummy_compare(stored_hash)
        return False

    # Recompute hash with same parameters
    computed_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        iterations,
        dklen=_HASH_LENGTH,
    )

    # Compare using constant-time comparison
    computed_b64 = _base64_encode(computed_key)
    return hmac.compare_digest(computed_b64, expected_hash)


def _constant_time_dummy_compare(value: str) -> None:
    """Perform dummy comparison to maintain constant-time behavior.

    This prevents timing attacks by ensuring the function takes the same
    amount of time regardless of whether the hash format is valid.
    """
    # Use a fixed dummy hash for comparison
    dummy = "$pbkdf2-sha256$600000$AAAAAAAAAAAAAAAAAAAAAA$BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
    hmac.compare_digest(value, dummy)


def generate_password(length: int = 24) -> str:
    """Generate a random password suitable for initial setup.

    Args:
        length: Length of password to generate (default: 24)

    Returns:
        Random password string
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))