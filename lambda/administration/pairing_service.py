"""Generacion administrativa por demanda, con una sola ventana por usuario."""
import secrets
import time
import uuid

from botocore.exceptions import BotoCoreError, ClientError

from services.errors import ServiceError, UserError
from services.pairing_policy import PIN_GENERATION_ATTEMPTS, PIN_LIFETIME_SECONDS, PIN_MAX_ATTEMPTS, pairing_window_key
from services.validation import pairing_key, validate_thing, validate_user


class PairingAdminService:
    def __init__(self, dynamodb, iot, table_name, clock=time.time):
        self.dynamodb = dynamodb
        self.iot = iot
        self.table_name = table_name
        self.clock = clock

    def generate(self, user_id, thing):
        validate_user(user_id)
        validate_thing(thing)
        try:
            self.iot.describe_thing(thingName=thing)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                raise UserError("El Thing solicitado no existe.") from exc
            raise ServiceError() from exc
        except BotoCoreError as exc:
            raise ServiceError() from exc
        # Solo reintentar colisiones de PIN, nunca fallos de red ni ventanas activas.
        for _ in range(PIN_GENERATION_ATTEMPTS):
            now = int(self.clock())
            pin = str(1000 + secrets.randbelow(9000))
            key = pairing_key(pin)
            generation = str(uuid.uuid4())
            expires = now + PIN_LIFETIME_SECONDS
            window = {
                "userId": {"S": pairing_window_key(user_id)}, "recordType": {"S": "pairing_window"},
                "thingName": {"S": thing}, "pairKey": {"S": key}, "generation": {"S": generation},
                "expiresAt": {"N": str(expires)}, "remainingAttempts": {"N": str(PIN_MAX_ATTEMPTS)},
                "status": {"S": "active"},
            }
            pairing = {
                "userId": {"S": key}, "recordType": {"S": "pairing"},
                "thingName": {"S": thing}, "allowedUserId": {"S": user_id},
                "expiresAt": {"N": str(expires)}, "generation": {"S": generation},
            }
            def put(item, record_type):
                return {"Put": {
                    "TableName": self.table_name, "Item": item,
                    "ConditionExpression": "attribute_not_exists(userId) OR (recordType = :type AND expiresAt <= :now)",
                    "ExpressionAttributeValues": {":type": {"S": record_type}, ":now": {"N": str(now)}},
                }}
            try:
                self.dynamodb.transact_write_items(
                    TransactItems=[put(window, "pairing_window"), put(pairing, "pairing")],
                    ClientRequestToken=generation,
                )
                # Nunca loguear este retorno: solo lo recibe el operador IAM autorizado.
                return {"codigo": pin, "thingName": thing, "expiresInSeconds": PIN_LIFETIME_SECONDS}
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                    reasons = exc.response.get("CancellationReasons", [])
                    if reasons and reasons[0].get("Code") == "ConditionalCheckFailed":
                        raise UserError("Ya existe una ventana de vinculación para este usuario. Espera cinco minutos desde su generación; no se repone el presupuesto de intentos.") from exc
                    if len(reasons) == 2 and reasons[1].get("Code") == "ConditionalCheckFailed" and reasons[0].get("Code") in {"None", None}:
                        continue
                raise ServiceError() from exc
            except BotoCoreError as exc:
                raise ServiceError() from exc
        raise UserError("No se pudo reservar un PIN tras tres colisiones. Intenta más tarde.")
