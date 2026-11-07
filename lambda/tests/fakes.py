"""Modelo en memoria con lock y commit atomico; no emula todo DynamoDB."""
import copy
import threading

from botocore.exceptions import ClientError


def error(code):
    return ClientError({"Error": {"Code": code, "Message": "PRIVATE_VALUE_MUST_NOT_LEAK"}}, "TestOperation")


def scalar(item, key):
    attribute = item.get(key, {})
    if "N" in attribute:
        return int(attribute["N"])
    return attribute.get("S")


class AtomicDynamo:
    def __init__(self):
        self.items = {}
        self.lock = threading.RLock()
        self.reservations = 0

    def get_item(self, **kw):
        with self.lock:
            item = self.items.get(kw["Key"]["userId"]["S"])
            return {"Item": copy.deepcopy(item)} if item else {}

    def update_item(self, **kw):
        with self.lock:
            assert kw["UpdateExpression"] == "SET remainingAttempts = remainingAttempts - :one"
            assert kw["ConditionExpression"] == "recordType = :type AND #status = :active AND expiresAt > :now AND remainingAttempts > :zero"
            key = kw["Key"]["userId"]["S"]
            item = self.items.get(key, {})
            v = kw["ExpressionAttributeValues"]
            allowed = (scalar(item, "recordType") == scalar(v, ":type") and
                       scalar(item, "status") == scalar(v, ":active") and
                       scalar(item, "expiresAt") > scalar(v, ":now") and
                       scalar(item, "remainingAttempts") > scalar(v, ":zero"))
            if not allowed:
                raise error("ConditionalCheckFailedException")
            item["remainingAttempts"] = {"N": str(scalar(item, "remainingAttempts")-scalar(v, ":one"))}
            self.reservations += 1
            return {"Attributes": copy.deepcopy(item)}

    def _allowed(self, operation, data):
        item_key = data.get("Key", data.get("Item"))["userId"]["S"]
        old = self.items.get(item_key, {})
        condition = data["ConditionExpression"]
        values = data.get("ExpressionAttributeValues", {})
        if operation == "Put":
            if condition.startswith("attribute_not_exists(userId) OR"):
                assert condition == "attribute_not_exists(userId) OR (recordType = :type AND expiresAt <= :now)"
                return not old or (scalar(old, "recordType") == scalar(values, ":type") and
                                   scalar(old, "expiresAt") <= scalar(values, ":now"))
            if condition == "attribute_not_exists(userId)":
                return not old
            assert condition in ("thingName = :old AND revision = :revision", "thingName = :old AND attribute_not_exists(revision)")
            return bool(old and scalar(old, "thingName") == scalar(values, ":old") and
                        old.get("revision") == values.get(":revision"))
        if operation == "Delete":
            assert condition == "recordType = :type AND allowedUserId = :user AND thingName = :thing AND expiresAt = :expiry AND expiresAt > :now AND generation = :generation"
            return bool(old and all(scalar(old, field) == scalar(values, parameter) for field, parameter in (
                ("recordType", ":type"), ("allowedUserId", ":user"), ("thingName", ":thing"),
                ("expiresAt", ":expiry"), ("generation", ":generation"))) and
                scalar(old, "expiresAt") > scalar(values, ":now"))
        assert operation == "Update"
        assert condition == "recordType = :type AND #status = :active AND generation = :generation AND pairKey = :key AND expiresAt > :now"
        return bool(old and all(scalar(old, field) == scalar(values, parameter) for field, parameter in (
            ("recordType", ":type"), ("status", ":active"), ("generation", ":generation"), ("pairKey", ":key"))) and
            scalar(old, "expiresAt") > scalar(values, ":now"))

    def transact_write_items(self, **kw):
        with self.lock:
            actions = [next(iter(item.items())) for item in kw["TransactItems"]]
            allowed = [self._allowed(operation, data) for operation, data in actions]
            if not all(allowed):
                exc = error("TransactionCanceledException")
                exc.response["CancellationReasons"] = [{"Code": "None" if valid else "ConditionalCheckFailed"} for valid in allowed]
                raise exc
            for operation, data in actions:
                key = data.get("Key", data.get("Item"))["userId"]["S"]
                if operation == "Put":
                    self.items[key] = copy.deepcopy(data["Item"])
                elif operation == "Delete":
                    del self.items[key]
                else:
                    v = data["ExpressionAttributeValues"]
                    self.items[key]["status"] = copy.deepcopy(v[":consumed"])
                    self.items[key]["remainingAttempts"] = copy.deepcopy(v[":zero"])
            return {}

    def delete_item(self, **kw):
        with self.lock:
            key = kw["Key"]["userId"]["S"]
            if "thingName" not in self.items.get(key, {}):
                raise error("ConditionalCheckFailedException")
            return {"Attributes": self.items.pop(key)}
