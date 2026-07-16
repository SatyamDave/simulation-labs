"""Project API keys. STUB — Agent P2-C. Signatures + format FROZEN.

Format: ``sl_live_<prefix8>_<secret32>``. The DB stores the visible ``prefix``
(``sl_live_<prefix8>``, indexed for lookup) and a hash of the FULL key. The
plaintext is shown to the user exactly once at creation.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

KEY_PREFIX = "sl_live_"

# Length (in hex chars) of the visible id segment that follows KEY_PREFIX.
_PREFIX_LEN = 8


def generate_api_key() -> tuple[str, str, str]:
    """Return (prefix, plaintext, key_hash). ``prefix`` is 'sl_live_<8>' (stored,
    indexed); ``plaintext`` is the full key (shown once); ``key_hash`` is stored."""
    prefix_id = secrets.token_hex(_PREFIX_LEN // 2)          # 8 hex chars
    secret = secrets.token_urlsafe(24)                       # ~32 url-safe chars
    prefix = f"{KEY_PREFIX}{prefix_id}"
    plaintext = f"{prefix}_{secret}"
    return prefix, plaintext, hash_api_key(plaintext)


def prefix_of(plaintext: str) -> str:
    """Extract the indexed 'sl_live_<8>' prefix from a full key (for DB lookup)."""
    if not isinstance(plaintext, str) or not plaintext.startswith(KEY_PREFIX):
        return ""
    rest = plaintext[len(KEY_PREFIX):]
    prefix_id = rest.split("_", 1)[0]
    if len(prefix_id) != _PREFIX_LEN:
        return ""
    return f"{KEY_PREFIX}{prefix_id}"


def hash_api_key(plaintext: str) -> str:
    """Hash a full key for storage (sha256 hex is fine — keys are high-entropy)."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def verify_api_key(plaintext: str, key_hash: str) -> bool:
    """Constant-time compare; never raise."""
    try:
        return hmac.compare_digest(hash_api_key(plaintext), key_hash)
    except (TypeError, AttributeError):
        return False


__all__ = ["KEY_PREFIX", "generate_api_key", "prefix_of", "hash_api_key", "verify_api_key"]
