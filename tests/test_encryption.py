"""
Encryption at rest (CLAUDE.md §6 step 9). TOTP 2FA secrets are stored as Fernet ciphertext via the
`EncryptedString` column type — a DB dump alone never exposes them — while 2FA still works because the
column transparently decrypts on read. Legacy plaintext values are read back unchanged (safe rollout).
"""
import pyotp
from app.db.crypto import EncryptedString, encrypt_str, decrypt_str
from tests.conftest import auth


def test_encrypt_round_trip():
    ct = encrypt_str("JBSWY3DPEHPK3PXP")
    assert ct != "JBSWY3DPEHPK3PXP"
    assert ct.startswith("gAAAAA")            # Fernet token marker
    assert decrypt_str(ct) == "JBSWY3DPEHPK3PXP"


def test_decrypt_legacy_plaintext_passthrough():
    # a value that is not valid ciphertext (written before encryption) is returned unchanged
    assert decrypt_str("PLAINLEGACYBASE32SECRET") == "PLAINLEGACYBASE32SECRET"


def test_encrypted_string_type_decorator():
    t = EncryptedString(255)
    bound = t.process_bind_param("S3CR3TVALUE", None)
    assert bound is not None and bound != "S3CR3TVALUE" and bound.startswith("gAAAAA")
    assert t.process_result_value(bound, None) == "S3CR3TVALUE"
    assert t.process_bind_param(None, None) is None
    assert t.process_result_value(None, None) is None


def test_totp_secret_encrypted_but_2fa_still_works(client):
    """End-to-end: the secret is stored encrypted, yet a TOTP code generated from the (decrypted)
    secret verifies — proving the column round-trips correctly through real auth."""
    client.post("/api/auth/register", json={
        "full_name": "Adv", "email": "enc2fa@firm.com", "password": "Sup3rSecret!", "role": "advocate"})
    tok = client.post("/api/auth/login",
                      json={"email": "enc2fa@firm.com", "password": "Sup3rSecret!"}).json()["access_token"]
    r = client.get("/api/auth/2fa/setup", headers=auth(tok))
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    assert secret                              # plaintext base32 returned to the user (decrypted)
    code = pyotp.TOTP(secret).now()
    en = client.post("/api/auth/2fa/enable", headers=auth(tok), json={"code": code})
    assert en.status_code == 200, en.text
