import hashlib
import hmac
import os
import secrets
import time
from app.config import settings

def generate_pin() -> str:
    """Generate a 6-digit PIN string (e.g. '849201')."""
    return f"{secrets.randbelow(900000) + 100000}"

def hash_pin(pin: str, salt: bytes | None = None) -> tuple[str, str]:
    """
    Hash PIN using PBKDF2-HMAC-SHA256 with 100,000 iterations.
    Returns (hex_hash, hex_salt).
    """
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100000)
    return dk.hex(), salt.hex()

def verify_pin(pin: str, hex_hash: str, hex_salt: str) -> bool:
    """Verify input PIN against stored PBKDF2 hash and salt."""
    try:
        salt = bytes.fromhex(hex_salt)
        computed_hash, _ = hash_pin(pin, salt)
        return hmac.compare_digest(computed_hash, hex_hash)
    except Exception:
        return False

def create_session_token(upload_id: str) -> str:
    """
    Create a signed session token for authenticated download session.
    Format: upload_id:timestamp:signature
    """
    ts = str(int(time.time()))
    payload = f"{upload_id}:{ts}".encode("utf-8")
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{upload_id}:{ts}:{sig}"

def verify_session_token(token: str, upload_id: str) -> bool:
    """Verify session token signature and expiration."""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        tok_upload_id, ts_str, sig = parts
        if tok_upload_id != upload_id:
            return False
        
        # Check token age
        ts = int(ts_str)
        max_age = settings.SESSION_MAX_AGE_HOURS * 3600
        if time.time() - ts > max_age or time.time() < ts - 60:
            return False
        
        # Verify HMAC
        payload = f"{tok_upload_id}:{ts_str}".encode("utf-8")
        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False
