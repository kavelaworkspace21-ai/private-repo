import pyotp
import qrcode
import io
import base64
from app.auth.config import APP_NAME


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp_code(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    # valid=1 allows ±30s drift
    return totp.verify(code, valid_window=1)


def get_totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=APP_NAME)


def get_qr_code_base64(secret: str, email: str) -> str:
    uri = get_totp_uri(secret, email)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
