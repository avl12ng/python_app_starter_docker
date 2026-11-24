"""Double authentification TOTP (RFC 6238) : Google Authenticator, FreeOTP, Microsoft Authenticator…"""

from __future__ import annotations

import re
import time

import pyotp
import qrcode
import qrcode.image.svg

PERIOD = 30
WINDOW = 1  # tolère un pas de 30 s d'avance ou de retard


def generate_secret() -> str:
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret, interval=PERIOD).provisioning_uri(name=account, issuer_name=issuer)


def verify(secret: str, code: str, last_step: int | None = None) -> int | None:
    """Renvoie le pas de temps accepté (à mémoriser contre le rejeu), ou None si le code est refusé."""
    code = re.sub(r"\s+", "", code or "")
    if not re.fullmatch(r"\d{6}", code) or not secret:
        return None
    totp = pyotp.TOTP(secret, interval=PERIOD)
    now_step = int(time.time()) // PERIOD
    for offset in range(-WINDOW, WINDOW + 1):
        step = now_step + offset
        if last_step is not None and step <= last_step:
            continue
        if pyotp.utils.strings_equal(totp.generate_otp(step), code):
            return step
    return None


def qr_svg(uri: str) -> str:
    """QR code en SVG généré localement (aucun service externe, compatible avec la CSP)."""
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return img.to_string(encoding="unicode")
