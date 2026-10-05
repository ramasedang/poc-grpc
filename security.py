"""Deliberately broken auth helpers (OWASP A07 - Identification & Auth Failures).

Two planted flaws:
  1. Weak, hard-coded HS256 secret.
  2. Tokens signed with `alg: none` are accepted (signature bypass).
"""
import jwt

# Hard-coded, guessable signing secret (leaked by the Debug RPC too).
JWT_SECRET = "secret"


def issue_token(user: dict) -> str:
    payload = {
        "sub": user["username"],
        "uid": user["id"],
        "role": user["role"],
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """Insecure verification.

    Accepts `none` alg and does not enforce the expected algorithm, so an
    attacker can forge an admin token with no signature.
    """
    if not token:
        return None
    try:
        # BUG: 'none' is allowed and no signature is required for it.
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256", "none"],
            options={"verify_signature": False} if _is_alg_none(token) else {},
        )
    except Exception:
        return None


def _is_alg_none(token: str) -> bool:
    try:
        header = jwt.get_unverified_header(token)
        return str(header.get("alg", "")).lower() == "none"
    except Exception:
        return False
