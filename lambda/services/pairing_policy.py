"""Politica fija compartida: no ampliable desde un intent o evento administrativo."""
import hashlib

from .validation import validate_user

PIN_LIFETIME_SECONDS = 300
PIN_MAX_ATTEMPTS = 3
PIN_GENERATION_ATTEMPTS = 3


def pairing_window_key(user_id):
    validate_user(user_id)
    return "PAIRUSER#" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()
