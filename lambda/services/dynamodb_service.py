"""Acceso por clave. Un código autorizado se consume junto con la vinculación."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import time
import hmac
from typing import NamedTuple
import uuid

from botocore.exceptions import BotoCoreError, ClientError

from .errors import ServiceError, UserError
from .validation import pairing_key, validate_thing, validate_user
from .pairing_policy import PIN_LIFETIME_SECONDS, pairing_window_key


@dataclass(frozen=True)
class Binding:
    thing_name: str
    revision: str | None = None


class PairingAuthorization(NamedTuple):
    key: str
    thing_name: str
    expires_at: int
    generation: str


class DynamoDBService:
    def __init__(self, client, table_name, clock=time.time):
        self.client = client
        self.table_name = table_name
        self.clock = clock

    def _get(self, key):
        try:
            return self.client.get_item(
                TableName=self.table_name, Key={"userId": {"S": key}}, ConsistentRead=True
            ).get("Item")
        except (BotoCoreError, ClientError) as exc:
            raise ServiceError() from exc

    def get_binding(self, user_id):
        validate_user(user_id)
        item = self._get(user_id)
        if not item:
            return None
        try:
            thing = validate_thing(item["thingName"]["S"])
            if "recordType" in item and item["recordType"] != {"S": "binding"}:
                raise ValueError("record type")
            revision = item["revision"]["S"] if "revision" in item else None
            if revision is not None and (not isinstance(revision, str) or not revision):
                raise ValueError("revision")
            return Binding(thing, revision)
        except (KeyError, TypeError, ValueError) as exc:
            raise UserError("La vinculación guardada no es válida. Desvincula y vuelve a vincular.") from exc

    def authorize_code(self, user_id, code):
        """Reservar un intento ANTES de comparar el PIN. Nunca reponerlo por fallo."""
        validate_user(user_id)
        key = pairing_key(code)
        now = int(self.clock())
        denial = "El código no es válido, caducó, no está autorizado o se agotaron los intentos. Solicita ayuda al administrador."
        try:
            result = self.client.update_item(
                TableName=self.table_name, Key={"userId": {"S": pairing_window_key(user_id)}},
                UpdateExpression="SET remainingAttempts = remainingAttempts - :one",
                ConditionExpression="recordType = :type AND #status = :active AND expiresAt > :now AND remainingAttempts > :zero",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":type": {"S": "pairing_window"}, ":active": {"S": "active"},
                                           ":now": {"N": str(now)}, ":one": {"N": "1"}, ":zero": {"N": "0"}},
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise UserError(denial) from exc
            raise ServiceError() from exc
        except BotoCoreError as exc:
            raise ServiceError() from exc
        try:
            window = result["Attributes"]
            if not hmac.compare_digest(key, window["pairKey"]["S"]):
                raise ValueError("mismatch")
            generation = window["generation"]["S"]
            expires = int(window["expiresAt"]["N"])
            thing = validate_thing(window["thingName"]["S"])
            if not isinstance(generation, str) or not generation or not now < expires <= now + PIN_LIFETIME_SECONDS:
                raise ValueError("window")
        except (KeyError, TypeError, ValueError, UserError) as exc:
            raise UserError(denial) from exc
        item = self._get(key)  # Solo consultar PAIR si coincide el hash de la ventana del usuario.
        try:
            if (
                item["recordType"]["S"] != "pairing"
                or item["allowedUserId"]["S"] != user_id
                or item["thingName"]["S"] != thing
                or item["generation"]["S"] != generation
                or int(item["expiresAt"]["N"]) != expires
            ):
                raise ValueError("authorization")
        except (KeyError, TypeError, ValueError) as exc:
            raise UserError(denial) from exc
        return PairingAuthorization(key, thing, expires, generation)

    def save_binding(self, user_id, authorization, previous):
        validate_user(user_id)
        key, thing, expires, generation = authorization
        validate_thing(thing)
        now = int(self.clock())
        if expires <= now:
            raise UserError("El código caducó. Solicita uno nuevo al administrador.")
        item = {
            "userId": {"S": user_id}, "thingName": {"S": thing},
            "recordType": {"S": "binding"}, "revision": {"S": str(uuid.uuid4())},
            "fechaVinculacion": {"S": datetime.fromtimestamp(now, timezone.utc).isoformat().replace("+00:00", "Z")},
        }
        put = {"TableName": self.table_name, "Item": item}
        if previous is None:
            put["ConditionExpression"] = "attribute_not_exists(userId)"
        else:
            put["ConditionExpression"] = "thingName = :old AND " + (
                "revision = :revision" if previous.revision else "attribute_not_exists(revision)"
            )
            put["ExpressionAttributeValues"] = {":old": {"S": previous.thing_name}}
            if previous.revision:
                put["ExpressionAttributeValues"][":revision"] = {"S": previous.revision}
        delete = {
            "TableName": self.table_name, "Key": {"userId": {"S": key}},
            "ConditionExpression": "recordType = :type AND allowedUserId = :user AND thingName = :thing AND expiresAt = :expiry AND expiresAt > :now AND generation = :generation",
            "ExpressionAttributeValues": {
                ":type": {"S": "pairing"}, ":user": {"S": user_id}, ":thing": {"S": thing},
                ":expiry": {"N": str(expires)}, ":now": {"N": str(now)}, ":generation": {"S": generation},
            },
        }
        consume_window = {
            "TableName": self.table_name, "Key": {"userId": {"S": pairing_window_key(user_id)}},
            "UpdateExpression": "SET #status = :consumed, remainingAttempts = :zero",
            "ConditionExpression": "recordType = :type AND #status = :active AND generation = :generation AND pairKey = :key AND expiresAt > :now",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":type": {"S": "pairing_window"}, ":active": {"S": "active"},
                ":consumed": {"S": "consumed"}, ":zero": {"N": "0"}, ":generation": {"S": generation},
                ":key": {"S": key}, ":now": {"N": str(now)}},
        }
        # Token por transaccion, sin retries de aplicacion; no es cache de eventos Alexa.
        token = hashlib.sha256(item["revision"]["S"].encode()).hexdigest()[:36]
        try:
            self.client.transact_write_items(
                TransactItems=[{"Delete": delete}, {"Put": put}, {"Update": consume_window}], ClientRequestToken=token
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"TransactionCanceledException", "ConditionalCheckFailedException"}:
                reasons = exc.response.get("CancellationReasons", [])
                if code == "ConditionalCheckFailedException" or any(r.get("Code") == "ConditionalCheckFailed" for r in reasons):
                    raise UserError("La vinculación cambió o el código ya se usó. Comprueba tu vinculación y solicita un código nuevo.") from exc
            raise ServiceError() from exc
        except BotoCoreError as exc:
            raise ServiceError() from exc

    def delete_binding(self, user_id):
        validate_user(user_id)
        try:
            self.client.delete_item(
                TableName=self.table_name, Key={"userId": {"S": user_id}},
                ConditionExpression="attribute_exists(thingName)", ReturnValues="ALL_OLD",
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise ServiceError() from exc
        except BotoCoreError as exc:
            raise ServiceError() from exc
