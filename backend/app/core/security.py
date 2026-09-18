"""
Password/session helpers for this project's demo-grade account system.

NOT FOR REAL SECURITY. This project's accounts use a 2-digit numeric PIN
(100 possible values) by deliberate product decision — a real attacker
with any ability to attempt logins would exhaust that space in seconds
regardless of how the PIN is hashed. hash_pin() still uses a salted SHA-256
hash rather than storing the PIN in plaintext, because that costs nothing
and is simply good hygiene — it is not a claim that this makes the account
system secure. If this project ever needs real account security (a public
deployment, real user data at stake), the fix is a real password policy
plus a slow, purpose-built password hash (argon2/bcrypt via passlib) —
not a stronger hash of the same 2-digit PIN.
"""

import hashlib
import hmac
import secrets

_PIN_HASH_ITERATIONS = 100_000


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), _PIN_HASH_ITERATIONS).hex()


def generate_salt() -> str:
    return secrets.token_hex(16)


def verify_pin(pin: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_pin(pin, salt), expected_hash)


def generate_session_token() -> str:
    return secrets.token_hex(32)
