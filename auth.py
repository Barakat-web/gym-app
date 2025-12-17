"""
auth.py
Authentication utilities (bcrypt hashing, verify, login, change password).

This avoids passlib's bcrypt backend auto-detection issues on some Python 3.13 Windows setups.
"""

from __future__ import annotations

import bcrypt
import db


def _to_bcrypt_secret(password: str) -> bytes:
    """
    bcrypt only uses the first 72 BYTES of the password.
    We truncate to 72 bytes to avoid ValueError and to make behavior explicit.
    """
    pw = password.encode("utf-8")
    if len(pw) > 72:
        pw = pw[:72]
    return pw


def hash_password(password: str) -> str:
    """
    Returns a bcrypt hash as a UTF-8 string (stored in SQLite).
    """
    secret = _to_bcrypt_secret(password)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(secret, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify password against stored bcrypt hash.
    """
    secret = _to_bcrypt_secret(password)
    stored = password_hash.encode("utf-8")
    return bcrypt.checkpw(secret, stored)


def get_admin_by_username(username: str):
    return db.fetch_one("SELECT * FROM admin_users WHERE username = ?", (username,))


def login(username: str, password: str) -> bool:
    admin = get_admin_by_username(username)
    if not admin:
        return False
    return verify_password(password, admin["password_hash"])


def change_password(username: str, new_password: str) -> None:
    new_hash = hash_password(new_password)
    db.execute(
        "UPDATE admin_users SET password_hash = ? WHERE username = ?",
        (new_hash, username),
    )
    db.clear_force_password_change()
