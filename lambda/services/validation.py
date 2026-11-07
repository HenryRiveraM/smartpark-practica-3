import hashlib
import re

from .errors import UserError

USER_PATTERN = re.compile(r"amzn1\.ask\.account\.[A-Za-z0-9._:-]{1,1000}\Z", re.ASCII)
THING_PATTERN = re.compile(r"[A-Za-z0-9:_-]{1,128}\Z", re.ASCII)


def validate_user(value):
    if not isinstance(value, str) or not USER_PATTERN.fullmatch(value):
        raise UserError("No pude identificar tu usuario de Alexa. Abre la skill de nuevo.")
    return value


def validate_thing(value):
    if not isinstance(value, str) or not THING_PATTERN.fullmatch(value):
        raise UserError("La vinculación del dispositivo no es válida. Contacta al administrador.")
    return value


def pairing_key(value):
    if not isinstance(value, str) or len(value) > 40:
        raise UserError("Indica un código de vinculación de cuatro dígitos.")
    code = re.sub(r"[ \t]", "", value)
    if not re.fullmatch(r"[1-9][0-9]{3}", code, flags=re.ASCII):
        raise UserError("Indica un código de vinculación de cuatro dígitos.")
    return "PAIR#" + hashlib.sha256(code.encode("ascii")).hexdigest()
