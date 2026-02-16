from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import shutil
import subprocess
import tempfile

try:
    import bcrypt as _bcrypt
except ModuleNotFoundError:  # pragma: no cover - exercised when bcrypt module is unavailable.
    _bcrypt = None

_BCRYPT_USER = "__auth__"
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_DEFAULT_PASSWORD_COST = 12
_MIN_PASSWORD_LENGTH = 8


class PasswordInputError(ValueError):
    """Raised when the submitted password is invalid."""


def normalize_password(password: str) -> str:
    normalized = (password or "").strip()
    if len(normalized) < _MIN_PASSWORD_LENGTH:
        raise PasswordInputError(f"password must be at least {_MIN_PASSWORD_LENGTH} characters")
    return normalized


def hash_password(password: str, *, cost: int = _DEFAULT_PASSWORD_COST) -> str:
    raw_password = normalize_password(password)
    normalized_cost = _normalize_cost(cost)

    if _bcrypt is not None:
        encoded = raw_password.encode("utf-8")
        return _bcrypt.hashpw(encoded, _bcrypt.gensalt(rounds=normalized_cost)).decode("utf-8")

    htpasswd_path = shutil.which("htpasswd")
    if htpasswd_path:
        return _hash_with_htpasswd(htpasswd_path, raw_password, normalized_cost)

    return _hash_with_bcrypt_fallback(raw_password, normalized_cost)


def verify_password(password: str, hashed_password: str) -> bool:
    raw_password = normalize_password(password)
    if not _looks_like_bcrypt(hashed_password):
        return False

    if _bcrypt is not None:
        return _bcrypt.checkpw(raw_password.encode("utf-8"), hashed_password.encode("utf-8"))

    htpasswd_path = shutil.which("htpasswd")
    if htpasswd_path:
        return _verify_with_htpasswd(htpasswd_path, raw_password, hashed_password)

    return _verify_with_bcrypt_fallback(raw_password, hashed_password)


def _normalize_cost(cost: int) -> int:
    if cost < 4:
        return 4
    if cost > 16:
        return 16
    return cost


def _looks_like_bcrypt(value: str) -> bool:
    return value.startswith(_BCRYPT_PREFIXES) and len(value) >= 60


def _hash_with_htpasswd(htpasswd_path: str, password: str, cost: int) -> str:
    completed = subprocess.run(
        [htpasswd_path, "-nbBC", str(cost), _BCRYPT_USER, password],
        check=True,
        capture_output=True,
        text=True,
    )
    line = completed.stdout.strip()
    if ":" not in line:
        raise RuntimeError("failed to parse htpasswd output")
    _, _, password_hash = line.partition(":")
    return password_hash.strip()


def _verify_with_htpasswd(htpasswd_path: str, password: str, password_hash: str) -> bool:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".htpasswd", delete=False, encoding="utf-8") as handle:
        handle.write(f"{_BCRYPT_USER}:{password_hash}\n")
        temp_path = handle.name
    try:
        completed = subprocess.run(
            [htpasswd_path, "-vb", temp_path, _BCRYPT_USER, password],
            capture_output=True,
            text=True,
        )
        return completed.returncode == 0
    finally:
        os.remove(temp_path)


def _hash_with_bcrypt_fallback(password: str, cost: int) -> str:
    salt_part = _bcryptish_encode(secrets.token_bytes(16), expected_size=22)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_part.encode("utf-8"),
        max(cost * 10_000, 120_000),
        dklen=23,
    )
    hash_part = _bcryptish_encode(digest, expected_size=31)
    return f"$2b${cost:02d}${salt_part}{hash_part}"


def _verify_with_bcrypt_fallback(password: str, password_hash: str) -> bool:
    parts = password_hash.split("$")
    if len(parts) != 4:
        return False
    try:
        cost = int(parts[2])
    except ValueError:
        return False

    payload = parts[3]
    if len(payload) < 53:
        return False

    salt_part = payload[:22]
    expected_hash_part = payload[22:53]
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_part.encode("utf-8"),
        max(cost * 10_000, 120_000),
        dklen=23,
    )
    computed_hash_part = _bcryptish_encode(digest, expected_size=31)
    return hmac.compare_digest(expected_hash_part, computed_hash_part)


def _bcryptish_encode(value: bytes, *, expected_size: int) -> str:
    translated = base64.b64encode(value).decode("ascii").rstrip("=").translate(str.maketrans("+/", "./"))
    if len(translated) >= expected_size:
        return translated[:expected_size]
    return translated + ("." * (expected_size - len(translated)))
