"""Shadow clasico. Sin polling, sin consultas previas a una orden."""
import json
import math
import time

from botocore.exceptions import BotoCoreError, ClientError

from .errors import ServiceError, UserError
from .validation import validate_thing


class ShadowService:
    def __init__(self, iot_client, data_client_factory, max_age=180, clock=time.time):
        self.iot = iot_client
        self.data_client_factory = data_client_factory
        self.max_age = max_age
        self.clock = clock

    def describe_thing(self, thing):
        validate_thing(thing)
        try:
            self.iot.describe_thing(thingName=thing)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                raise UserError("El dispositivo autorizado ya no existe. Contacta al administrador.") from exc
            raise ServiceError() from exc
        except BotoCoreError as exc:
            raise ServiceError() from exc

    def get_reported(self, thing, field):
        validate_thing(thing)
        try:
            result = self.data_client_factory().get_thing_shadow(thingName=thing)
            body = result["payload"]
            try:
                raw = body.read(65537)
            finally:
                body.close()
            if len(raw) > 65536:
                raise ValueError("size")
            def reject_constant(_):
                raise ValueError("nonfinite")
            document = json.loads(raw, parse_constant=reject_constant)
            value = document["state"]["reported"][field]
            timestamp = document["metadata"]["reported"][field]["timestamp"]
            if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
                raise ValueError("timestamp")
            age = self.clock() - timestamp
            if age < -30 or age > self.max_age:
                raise UserError("El último dato del dispositivo está desactualizado. No puedo confirmar su estado actual.")
            return value
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                raise UserError("El dispositivo todavía no tiene un Shadow disponible.") from exc
            raise ServiceError() from exc
        except BotoCoreError as exc:
            raise ServiceError() from exc
        except (KeyError, TypeError, ValueError, UnicodeError, AttributeError) as exc:
            raise UserError("No tengo un dato reportado válido y reciente del dispositivo.") from exc

    def set_barrier(self, thing, state):
        validate_thing(thing)
        if state not in {"abierta", "cerrada"}:
            raise ValueError("Unsupported barrier target")
        payload = json.dumps({"state": {"desired": {"barrera": state}}}, separators=(",", ":")).encode()
        try:
            response = self.data_client_factory().update_thing_shadow(thingName=thing, payload=payload)
            body = response.get("payload")
            if body is not None:
                body.close()
        except (BotoCoreError, ClientError) as exc:
            raise ServiceError() from exc
