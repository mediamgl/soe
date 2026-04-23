"""Symmetric encryption for stored LLM API keys (Fernet / AES-128-CBC + HMAC)."""
import os
from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("SETTINGS_ENCRYPTION_KEY missing from environment.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_str(plaintext: str) -> str:
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""
    except Exception:
        return ""
