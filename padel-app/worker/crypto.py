"""AES-256-GCM at-rest encryption — Python side (mirror of web/lib/crypto.ts).

Format:  enc1.<base64(iv)>.<base64(ciphertext)>.<base64(tag)>
Key:     data/secret.key (hex), shared with the web tier.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_PATH = os.environ.get("PADEL_KEY_PATH") or str(
    Path(__file__).resolve().parent.parent / "data" / "secret.key"
)
_PREFIX = "enc1."


def _key() -> bytes:
    return bytes.fromhex(Path(KEY_PATH).read_text().strip())


def is_encrypted(s: str) -> bool:
    return isinstance(s, str) and s.startswith(_PREFIX)


def encrypt(plain: str) -> str:
    iv = os.urandom(12)
    blob = AESGCM(_key()).encrypt(iv, plain.encode("utf-8"), None)  # ciphertext + tag
    ct, tag = blob[:-16], blob[-16:]
    parts = (base64.b64encode(x).decode() for x in (iv, ct, tag))
    return _PREFIX + ".".join(parts)


def decrypt(s: str) -> str:
    """Decrypt an enc1 value; pass through anything not encrypted (legacy plaintext)."""
    if not is_encrypted(s):
        return s
    _, iv_b, ct_b, tag_b = s.split(".")
    iv = base64.b64decode(iv_b)
    ct = base64.b64decode(ct_b)
    tag = base64.b64decode(tag_b)
    return AESGCM(_key()).decrypt(iv, ct + tag, None).decode("utf-8")
