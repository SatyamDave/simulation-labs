"""Password hashing (bcrypt). STUB — Agent P2-C. Signatures FROZEN."""

from __future__ import annotations

import bcrypt

# bcrypt hashes at most the first 72 BYTES of input and errors on longer input
# in newer releases; truncate defensively so long passphrases never raise.
_BCRYPT_MAX_BYTES = 72


def _encode(password: str) -> bytes:
    """UTF-8 encode and truncate to bcrypt's 72-byte input limit."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash string for storage in User.password_hash."""
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verify; False on any mismatch or malformed hash (never raise)."""
    try:
        return bcrypt.checkpw(_encode(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError, AttributeError):
        return False


__all__ = ["hash_password", "verify_password"]
