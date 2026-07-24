"""
Application-level field encryption at rest (CLAUDE.md §6 step 9 "encryption at rest where practical").

Small high-value secrets (e.g. TOTP 2FA secrets) are stored as Fernet ciphertext, so a database
dump alone never exposes them. Use the `EncryptedString` column type for such fields.

Key resolution (in order):
  1. `FIELD_ENCRYPTION_KEY` env — a urlsafe-base64 32-byte Fernet key. **Set this in production.**
     Generate one with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. else a key derived deterministically from `JWT_SECRET` (dev/test convenience).

Decryption is backward-compatible: a value that is not valid ciphertext (legacy plaintext written
before encryption was enabled) is returned as-is, so the change rolls out without breaking old rows.

CAVEATS:
  • Rotating the key without re-encrypting existing values makes them undecryptable. For key rotation,
    decrypt-then-re-encrypt the affected rows under the new key.
  • This is field-level encryption. For full storage-level encryption on Aurora, enable RDS encryption
    (AWS KMS) at cluster creation — that is separate, infrastructure-level, and not done here.
"""
import os
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.auth.config import JWT_SECRET


def _fernet() -> Fernet:
    key = os.getenv("FIELD_ENCRYPTION_KEY")
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    # Dev/test fallback: a stable 32-byte Fernet key derived from JWT_SECRET.
    derived = base64.urlsafe_b64encode(hashlib.sha256(JWT_SECRET.encode()).digest())
    return Fernet(derived)


def encrypt_str(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_str(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return token  # legacy plaintext (pre-encryption) — return unchanged


class EncryptedString(TypeDecorator):
    """A String column whose value is transparently Fernet-encrypted at rest."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_str(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt_str(value)
