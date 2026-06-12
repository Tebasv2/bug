import os
import base64
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.environ.get("WALLET_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("WALLET_ENCRYPTION_KEY env var not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_private_key(private_key_hex: str) -> str:
    f = _get_fernet()
    return f.encrypt(private_key_hex.encode()).decode()


def decrypt_private_key(encrypted: str) -> str:
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()
