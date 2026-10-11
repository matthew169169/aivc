"""Shared-password authentication helpers for the Omics-GEM API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, Response


AUTH_COOKIE_NAME = "omics_gem_session"
HASH_ALGORITHM = "pbkdf2_sha256"
DEFAULT_HASH_ITERATIONS = 260_000
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60
FAILED_LOGIN_WINDOW_SECONDS = 5 * 60
FAILED_LOGIN_LIMIT = 5
TRUTHY = {"1", "true", "yes", "on", "enabled"}

_FAILED_LOGINS: dict[str, list[float]] = {}


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    password_hash: str
    session_secret: str
    session_ttl_seconds: int
    cookie_secure: bool

    @property
    def configured(self) -> bool:
        return (not self.enabled) or bool(self.password_hash and self.session_secret)


def get_auth_config() -> AuthConfig:
    ttl_raw = os.environ.get("OMICS_GEM_SESSION_TTL_SECONDS", "")
    try:
        ttl = int(ttl_raw) if ttl_raw else DEFAULT_SESSION_TTL_SECONDS
    except ValueError:
        ttl = DEFAULT_SESSION_TTL_SECONDS
    return AuthConfig(
        enabled=os.environ.get("OMICS_GEM_AUTH_ENABLED", "").strip().lower() in TRUTHY,
        password_hash=os.environ.get("OMICS_GEM_PASSWORD_HASH", "").strip(),
        session_secret=os.environ.get("OMICS_GEM_SESSION_SECRET", "").strip(),
        session_ttl_seconds=max(300, ttl),
        cookie_secure=os.environ.get("OMICS_GEM_COOKIE_SECURE", "").strip().lower() in TRUTHY,
    )


def auth_status_from_request(request: Request | None = None) -> dict[str, Any]:
    config = get_auth_config()
    authenticated = False
    expires_at = 0
    if not config.enabled:
        authenticated = True
    elif config.configured and request is not None:
        payload = verify_session_token(request.cookies.get(AUTH_COOKIE_NAME, ""), config.session_secret)
        authenticated = bool(payload)
        expires_at = int(payload.get("exp", 0)) if payload else 0
    return {
        "auth_enabled": config.enabled,
        "configured": config.configured,
        "authenticated": authenticated,
        "expires_at": expires_at,
        "session_ttl_seconds": config.session_ttl_seconds,
    }


def hash_password(password: str, *, iterations: int = DEFAULT_HASH_ITERATIONS, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"{HASH_ALGORITHM}${iterations}${salt}${_base64_urlencode(digest)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected = encoded_hash.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        iterations = int(iterations_raw)
    except (ValueError, TypeError):
        return False
    actual = hash_password(password, iterations=iterations, salt=salt)
    return hmac.compare_digest(actual, encoded_hash)


def authenticate_password(password: str, request: Request) -> dict[str, Any]:
    config = get_auth_config()
    if not config.enabled:
        return auth_status_from_request(request)
    if not config.configured:
        raise HTTPException(status_code=503, detail="Authentication is enabled but not configured.")
    client_id = _client_id(request)
    if _is_rate_limited(client_id):
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again later.")
    if not verify_password(password, config.password_hash):
        _record_failed_login(client_id)
        raise HTTPException(status_code=401, detail="Invalid password.")
    _FAILED_LOGINS.pop(client_id, None)
    expires_at = int(time.time()) + config.session_ttl_seconds
    return {
        "auth_enabled": True,
        "configured": True,
        "authenticated": True,
        "expires_at": expires_at,
        "session_ttl_seconds": config.session_ttl_seconds,
        "token": create_session_token(config.session_secret, expires_at=expires_at),
    }


def create_session_token(secret: str, *, expires_at: int) -> str:
    payload = {
        "sub": "shared",
        "iat": int(time.time()),
        "exp": int(expires_at),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _base64_urlencode(payload_json)
    signature = _sign(payload_part, secret)
    return f"{payload_part}.{signature}"


def verify_session_token(token: str, secret: str) -> dict[str, Any] | None:
    if not token or "." not in token or not secret:
        return None
    payload_part, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload_part, secret), signature):
        return None
    try:
        payload = json.loads(_base64_urldecode(payload_part).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    if int(payload.get("exp", 0)) <= int(time.time()):
        return None
    return payload


def require_authenticated_request(request: Request) -> None:
    config = get_auth_config()
    if not config.enabled:
        return
    if not config.configured:
        raise HTTPException(status_code=503, detail="Authentication is enabled but not configured.")
    if verify_session_token(request.cookies.get(AUTH_COOKIE_NAME, ""), config.session_secret):
        return
    raise HTTPException(status_code=401, detail="Authentication required.")


def set_session_cookie(response: Response, token: str, *, expires_at: int) -> None:
    config = get_auth_config()
    max_age = max(0, int(expires_at) - int(time.time()))
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


def _sign(payload_part: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
    return _base64_urlencode(digest)


def _base64_urlencode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64_urldecode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _record_failed_login(client_id: str) -> None:
    now = time.time()
    window_start = now - FAILED_LOGIN_WINDOW_SECONDS
    attempts = [item for item in _FAILED_LOGINS.get(client_id, []) if item >= window_start]
    attempts.append(now)
    _FAILED_LOGINS[client_id] = attempts


def _is_rate_limited(client_id: str) -> bool:
    now = time.time()
    window_start = now - FAILED_LOGIN_WINDOW_SECONDS
    attempts = [item for item in _FAILED_LOGINS.get(client_id, []) if item >= window_start]
    _FAILED_LOGINS[client_id] = attempts
    return len(attempts) >= FAILED_LOGIN_LIMIT
