"""HMAC-signed session cookies for the in-app login.

Stateless: nothing in the database, no library beyond the stdlib. The cookie
value is `<payload>.<sig>` where payload is base64url-encoded JSON like
`{"v": 1, "iat": <issued-at-epoch>}` and sig is HMAC-SHA256 of the payload
keyed with SESSION_SECRET. Tampering invalidates the signature; sessions older
than SESSION_MAX_AGE are rejected on verify.

Single-password model: any verified cookie is "logged in." No identities yet —
when we add per-org or per-user auth, the payload is where that goes.
"""

import base64
import hmac
import hashlib
import json
import time

# 7 days. Bump if logins are too aggressive; trim if you want quicker re-auth.
SESSION_MAX_AGE = 7 * 24 * 60 * 60
SESSION_COOKIE_NAME = "session"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(s: str) -> bytes:
    # Re-pad before decoding — urlsafe_b64encode strips '=' for cookie cleanliness.
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_session(secret: str) -> str:
    payload = json.dumps({"v": 1, "iat": int(time.time())}, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(sig)}"


def verify_session(token: str | None, secret: str, max_age: int = SESSION_MAX_AGE) -> bool:
    if not token or not secret:
        return False
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64decode(payload_b64)
        sig = _b64decode(sig_b64)
    except Exception:
        return False

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return False

    try:
        data = json.loads(payload)
    except Exception:
        return False
    iat = data.get("iat")
    if not isinstance(iat, int):
        return False
    if int(time.time()) - iat > max_age:
        return False
    return True
