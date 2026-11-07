"""Sin sockets AWS: servicios reales con clientes dobles y eventos ASK completos."""
import copy
from datetime import datetime, timedelta, timezone
import io
import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch

from ask_sdk_core.serialize import DefaultSerializer
from ask_sdk_model.response_envelope import ResponseEnvelope
from botocore.exceptions import ClientError, ReadTimeoutError

import lambda_function
from services.dynamodb_service import Binding, DynamoDBService
from services.errors import ConfigurationError, ServiceError, UserError
from services.runtime import Backend, get_backend, validated_endpoint
from services.shadow_service import ShadowService
from services.validation import pairing_key
from services.pairing_policy import pairing_window_key
from fakes import AtomicDynamo

USER = "amzn1.ask.account.TEST_USER"
OTHER_USER = "amzn1.ask.account.OTHER_USER"
SKILL = "amzn1.ask.skill.00000000-0000-4000-8000-000000000000"
THING = "parqueo-del-usuario"  # Deliberadamente diferente al Thing del banco ESP32.
CODE = "1234"  # Codigo publico de pruebas; nunca registrar en AWS.
TABLE = "SmartParkBindings"


def aws_error(code, operation="TestOperation"):
    return ClientError({"Error": {"Code": code, "Message": "PRIVATE_VALUE_MUST_NOT_LEAK"}}, operation)


def event(intent=None, *, kind=None, user=USER, slots=None):
    request = {
        "type": kind or ("IntentRequest" if intent else "LaunchRequest"),
        "requestId": "amzn1.echo-api.request.test", "locale": "es-ES",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if intent:
        request["intent"] = {"name": intent, "confirmationStatus": "NONE", "slots": slots or {}}
        request["dialogState"] = "COMPLETED"
    system = {"application": {"applicationId": SKILL}, "user": {"userId": user},
              "device": {"deviceId": "test-device", "supportedInterfaces": {}}}
    return {"version": "1.0", "session": {"new": True, "sessionId": "test-session",
            "application": {"applicationId": SKILL}, "user": {"userId": user}, "attributes": {}},
            "context": {"System": system}, "request": request}


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ALEXA_SKILL_ID": SKILL, "TABLE_NAME": TABLE, "AWS_EC2_METADATA_DISABLED": "true"})
        self.env.start()
        self.no_aws = patch("boto3.client", side_effect=AssertionError("No AWS connections allowed"))
        self.no_aws_mock = self.no_aws.start()
        self.db = MagicMock()
        self.iot = MagicMock()
        self.data = MagicMock()
        self.factory = MagicMock(return_value=self.data)
        self.store = AtomicDynamo()
        self.items = self.store.items
        self.db.get_item.side_effect = self.store.get_item
        self.db.update_item.side_effect = self.store.update_item
        self.db.transact_write_items.side_effect = self.store.transact_write_items
        self.db.delete_item.side_effect = self.store.delete_item
        self.bindings = DynamoDBService(self.db, TABLE)
        self.shadow = ShadowService(self.iot, self.factory)
        self.backend = Backend(self.bindings, self.shadow)
        self.patch_backend = patch("handlers.common.get_backend", return_value=self.backend)
        self.patch_backend.start()
        # Los imports directos en estos modulos se parchean por separado.
        self.patches = [patch("handlers.binding_handlers.get_backend", return_value=self.backend),
                        patch("handlers.system_handlers.get_backend", return_value=self.backend)]
        for p in self.patches:
            p.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.no_aws.stop)
        self.addCleanup(self.patch_backend.stop)
        for p in self.patches:
            self.addCleanup(p.stop)
        self.addCleanup(get_backend.cache_clear)
        self.report()
        self.data.update_thing_shadow.return_value = {"payload": io.BytesIO(b"{}")}

    def bind(self, thing=THING, revision="old-revision"):
        self.items[USER] = {"userId": {"S": USER}, "thingName": {"S": thing}}
        if revision:
            self.items[USER]["revision"] = {"S": revision}

    def code(self, *, owner=USER, expiry=None, thing=THING):
        expires = str(expiry or int(time.time())+300)
        self.items[pairing_key(CODE)] = {
            "userId": {"S": pairing_key(CODE)}, "recordType": {"S": "pairing"},
            "allowedUserId": {"S": owner}, "expiresAt": {"N": expires},
            "thingName": {"S": thing}, "generation": {"S": "test-generation"},
        }
        self.items[pairing_window_key(owner)] = {
            "userId": {"S": pairing_window_key(owner)}, "recordType": {"S": "pairing_window"},
            "expiresAt": {"N": expires}, "thingName": {"S": thing}, "generation": {"S": "test-generation"},
            "pairKey": {"S": pairing_key(CODE)}, "status": {"S": "active"}, "remainingAttempts": {"N": "3"},
        }

    def report(self, *, value=12.5, presence=True, barrier="cerrada", age=5):
        now = int(time.time())
        self.document = {"state": {"desired": {"distancia_cm": 999, "barrera": "abierta"},
                         "reported": {"distancia_cm": value, "vehiculo_detectado": presence, "barrera": barrier}},
                         "metadata": {"reported": {field: {"timestamp": now-age} for field in ("distancia_cm", "vehiculo_detectado", "barrera")}},
                         "timestamp": now}
        self.data.get_thing_shadow.side_effect = lambda **_: {"payload": io.BytesIO(json.dumps(self.document).encode())}

    def invoke(self, intent=None, **kw):
        response = lambda_function.lambda_handler(event(intent, **kw), None)
        self.assertEqual(response["version"], "1.0")
        # Deserializar todas las respuestas mediante el SDK oficial.
        envelope = DefaultSerializer().deserialize(json.dumps(response), ResponseEnvelope)
        self.assertIsNotNone(envelope.response)
        speech = response.get("response", {}).get("outputSpeech", {})
        text = speech.get("ssml", speech.get("text", ""))
        self.assertNotIn("PRIVATE_VALUE", text)
        self.assertNotIn(USER, text)
        self.assertNotIn(CODE, text)
        return text

    def linking(self, intent="VincularParqueoIntent", code=CODE):
        return self.invoke(intent, slots={"codigo": {"name": "codigo", "value": code}})

    def test_launch_unbound(self):
        self.assertIn("código", self.invoke())
        self.db.get_item.assert_called_once_with(TableName=TABLE, Key={"userId": {"S": USER}}, ConsistentRead=True)
        self.factory.assert_not_called()

    def test_launch_bound(self):
        self.bind()
        self.assertIn("Bienvenido", self.invoke())
        self.iot.describe_thing.assert_not_called()

    def test_valid_binding_and_one_use_code(self):
        self.code()
        self.assertIn("quedó vinculado", self.linking())
        self.assertEqual(self.items[USER]["thingName"]["S"], THING)
        self.assertNotIn(pairing_key(CODE), self.items)
        self.iot.describe_thing.assert_called_once_with(thingName=THING)
        self.db.transact_write_items.assert_called_once()
        self.assertIn("Ya tienes", self.linking())
        self.assertEqual(self.db.transact_write_items.call_count, 1)

    def test_invalid_code_format(self):
        self.assertIn("cuatro dígitos", self.linking(code="arbitrary-thing"))
        self.iot.describe_thing.assert_not_called()
        self.assertEqual(self.db.get_item.call_count, 0)

    def test_missing_code_slot(self):
        self.assertIn("cuatro dígitos", self.invoke("VincularParqueoIntent"))

    def test_unknown_code(self):
        self.assertIn("no es válido", self.linking())
        self.iot.describe_thing.assert_not_called()

    def test_thing_name_is_not_authorization(self):
        self.assertIn("cuatro dígitos", self.linking(code=THING))
        self.db.transact_write_items.assert_not_called()

    def test_code_for_another_user(self):
        self.code(owner=OTHER_USER)
        self.assertIn("no es válido", self.linking())
        self.iot.describe_thing.assert_not_called()

    def test_expired_code(self):
        self.code(expiry=int(time.time())-1)
        self.assertIn("no es válido", self.linking())
        self.iot.describe_thing.assert_not_called()

    def test_overlong_code_lifetime(self):
        self.code(expiry=int(time.time())+3600)
        self.assertIn("no es válido", self.linking())

    def test_thing_not_found(self):
        self.code()
        self.iot.describe_thing.side_effect = aws_error("ResourceNotFoundException")
        self.assertIn("ya no existe", self.linking())
        self.db.transact_write_items.assert_not_called()
        self.assertIn(pairing_key(CODE), self.items)

    def test_no_binding_for_controls_or_queries(self):
        for intent in ("ConsultarDistanciaIntent", "ConsultarVehiculoIntent", "AbrirBarreraIntent", "CerrarBarreraIntent", "EstadoBarreraIntent"):
            with self.subTest(intent=intent):
                self.assertIn("No tienes", self.invoke(intent))
        self.factory.assert_not_called()

    def test_change_binding(self):
        self.bind(thing="old-device")
        self.code()
        self.assertIn("quedó vinculado", self.linking("CambiarVinculacionIntent"))
        put = self.db.transact_write_items.call_args.kwargs["TransactItems"][1]["Put"]
        self.assertIn("revision = :revision", put["ConditionExpression"])
        self.assertEqual(put["ExpressionAttributeValues"][":revision"], {"S": "old-revision"})
        self.assertEqual(self.items[USER]["thingName"]["S"], THING)

    def test_change_legacy_binding_without_revision(self):
        self.bind(thing="old-device", revision=None)
        self.code()
        self.assertIn("quedó vinculado", self.linking("CambiarVinculacionIntent"))

    def test_change_without_existing_binding(self):
        self.assertIn("Todavía no tienes", self.linking("CambiarVinculacionIntent"))
        self.db.transact_write_items.assert_not_called()

    def test_same_binding_consumes_pin(self):
        self.bind()
        self.code()
        self.assertIn("ya está vinculado", self.linking("CambiarVinculacionIntent"))
        self.db.transact_write_items.assert_called_once()
        self.assertNotIn(pairing_key(CODE), self.items)

    def test_transaction_conflict_does_not_consume_code(self):
        self.code()
        err = aws_error("TransactionCanceledException")
        err.response["CancellationReasons"] = [{"Code": "ConditionalCheckFailed"}]
        self.db.transact_write_items.side_effect = err
        self.assertIn("vinculación cambió", self.linking())
        self.assertIn(pairing_key(CODE), self.items)
        self.assertNotIn(USER, self.items)

    def test_binding_race_does_not_replace_newer_binding(self):
        self.bind(thing="old-device")
        self.code()
        previous = self.bindings.get_binding(USER)
        authorization = self.bindings.authorize_code(USER, CODE)
        self.items[USER]["revision"] = {"S": "concurrent-revision"}
        with self.assertRaises(UserError):
            self.bindings.save_binding(USER, authorization, previous)
        self.assertEqual(self.items[USER]["revision"]["S"], "concurrent-revision")
        self.assertIn(pairing_key(CODE), self.items)

    def test_unlinked_binding_is_not_recreated_by_stale_change(self):
        self.bind(thing="old-device")
        self.code()
        previous = self.bindings.get_binding(USER)
        authorization = self.bindings.authorize_code(USER, CODE)
        del self.items[USER]
        with self.assertRaises(UserError):
            self.bindings.save_binding(USER, authorization, previous)
        self.assertNotIn(USER, self.items)
        self.assertIn(pairing_key(CODE), self.items)

    def test_expiry_after_describe_prevents_commit(self):
        self.code()
        authorization = self.bindings.authorize_code(USER, CODE)
        self.bindings.clock = lambda: authorization[2]+1
        with self.assertRaises(UserError):
            self.bindings.save_binding(USER, authorization, None)
        self.db.transact_write_items.assert_not_called()

    def test_legacy_pairing_record_without_window_is_rejected(self):
        self.code()
        del self.items[pairing_window_key(USER)]
        self.assertIn("no es válido", self.linking())
        self.db.transact_write_items.assert_not_called()

    def test_logs_omit_user_code_and_aws_details(self):
        self.db.get_item.side_effect = aws_error("AccessDeniedException")
        with self.assertLogs("smartpark", level="WARNING") as logs:
            self.invoke("AbrirBarreraIntent")
        self.assertEqual(logs.output, ["WARNING:smartpark:request_failed type=ServiceError"])

    def test_transaction_service_error(self):
        self.code()
        self.db.transact_write_items.side_effect = aws_error("AccessDeniedException")
        self.assertIn("servicio", self.linking())

    def test_unbind_one_delete_no_get(self):
        self.bind()
        self.assertIn("Desvinculé", self.invoke("DesvincularParqueoIntent"))
        self.assertNotIn(USER, self.items)
        self.db.get_item.assert_not_called()
        self.db.delete_item.assert_called_once()

    def test_unbind_missing(self):
        self.assertIn("No tienes", self.invoke("DesvincularParqueoIntent"))

    def test_valid_distance_reported_not_desired(self):
        self.bind()
        self.assertIn("12,5 centímetros", self.invoke("ConsultarDistanciaIntent"))
        self.assertEqual(self.db.get_item.call_count, 1)
        self.data.get_thing_shadow.assert_called_once_with(thingName=THING)

    def test_invalid_distances(self):
        self.bind()
        for value in (-1, 0, 401, True, None, "12.5", [], float("nan"), float("inf")):
            with self.subTest(value=value):
                self.report(value=value)
                self.assertNotIn("centímetros", self.invoke("ConsultarDistanciaIntent"))

    def test_distance_integer_format(self):
        self.bind()
        self.report(value=120)
        self.assertIn("120 centímetros", self.invoke("ConsultarDistanciaIntent"))

    def test_presence_true_and_false(self):
        self.bind()
        for value, text in ((True, "hay un vehículo"), (False, "no hay un vehículo")):
            self.report(presence=value)
            self.assertIn(text, self.invoke("ConsultarVehiculoIntent"))

    def test_unknown_presence_not_absence(self):
        self.bind()
        for value in (None, 0, "false", {}):
            self.report(presence=value)
            self.assertIn("desconocida", self.invoke("ConsultarVehiculoIntent"))

    def test_open_and_close_only_desired(self):
        self.bind()
        for intent, state, action in (("AbrirBarreraIntent", "abierta", "abrir"), ("CerrarBarreraIntent", "cerrada", "cerrar")):
            self.assertIn("Solicité " + action, self.invoke(intent))
            args = self.data.update_thing_shadow.call_args.kwargs
            self.assertEqual(args["thingName"], THING)
            self.assertEqual(json.loads(args["payload"]), {"state": {"desired": {"barrera": state}}})
        self.data.get_thing_shadow.assert_not_called()
        self.assertEqual(self.data.update_thing_shadow.call_count, 2)

    def test_control_ignores_arbitrary_thing_slot(self):
        self.bind()
        self.invoke("AbrirBarreraIntent", slots={"thingName": {"name": "thingName", "value": "victim-device"}})
        self.assertEqual(self.data.update_thing_shadow.call_args.kwargs["thingName"], THING)

    def test_invalid_stored_thing_prevents_iot(self):
        self.bind(thing="../../victim")
        self.invoke("AbrirBarreraIntent")
        self.factory.assert_not_called()

    def test_wrong_record_type_prevents_control(self):
        self.bind()
        self.items[USER]["recordType"] = {"S": "pairing"}
        self.invoke("AbrirBarreraIntent")
        self.factory.assert_not_called()

    def test_malformed_revision_prevents_control(self):
        self.bind()
        self.items[USER]["revision"] = {"N": "1"}
        self.invoke("AbrirBarreraIntent")
        self.factory.assert_not_called()

    def test_barrier_state_reported(self):
        self.bind()
        self.assertIn("reportado, la barrera está cerrada", self.invoke("EstadoBarreraIntent"))
        self.report(barrier="abierta")
        self.assertIn("está abierta", self.invoke("EstadoBarreraIntent"))

    def test_unknown_barrier_state(self):
        self.bind()
        self.report(barrier="moviendo")
        self.assertIn("no ha informado", self.invoke("EstadoBarreraIntent"))

    def test_stale_per_field_even_when_document_is_new(self):
        self.bind()
        self.report(age=181)
        self.assertIn("desactualizado", self.invoke("ConsultarDistanciaIntent"))
        self.assertIn("desactualizado", self.invoke("EstadoBarreraIntent"))

    def test_missing_timestamp_does_not_fallback_to_document_time(self):
        self.bind()
        del self.document["metadata"]
        self.assertIn("No tengo", self.invoke("ConsultarDistanciaIntent"))

    def test_future_timestamp(self):
        self.bind()
        self.report(age=-60)
        self.assertIn("desactualizado", self.invoke("ConsultarVehiculoIntent"))

    def test_missing_reported_is_not_desired(self):
        self.bind()
        del self.document["state"]["reported"]
        self.assertIn("No tengo", self.invoke("ConsultarDistanciaIntent"))

    def test_invalid_json_and_oversize_close_stream(self):
        self.bind()
        for content in (b"not-json", b"[]", b"x"*65537):
            body = io.BytesIO(content)
            self.data.get_thing_shadow.side_effect = None
            self.data.get_thing_shadow.return_value = {"payload": body}
            self.assertIn("No tengo", self.invoke("ConsultarDistanciaIntent"))
            self.assertTrue(body.closed)

    def test_shadow_not_found(self):
        self.bind()
        self.data.get_thing_shadow.side_effect = aws_error("ResourceNotFoundException")
        self.assertIn("no tiene un Shadow", self.invoke("ConsultarDistanciaIntent"))

    def test_dynamodb_error_sanitized(self):
        self.db.get_item.side_effect = aws_error("AccessDeniedException")
        self.assertIn("servicio", self.invoke("AbrirBarreraIntent"))
        self.factory.assert_not_called()

    def test_dynamodb_delete_error_sanitized(self):
        self.db.delete_item.side_effect = aws_error("AccessDeniedException")
        self.assertIn("servicio", self.invoke("DesvincularParqueoIntent"))

    def test_iot_get_error_sanitized(self):
        self.bind()
        self.data.get_thing_shadow.side_effect = aws_error("UnauthorizedException")
        self.assertIn("servicio", self.invoke("ConsultarDistanciaIntent"))

    def test_iot_update_timeout_no_retry(self):
        self.bind()
        self.data.update_thing_shadow.side_effect = ReadTimeoutError(endpoint_url="https://test.invalid")
        self.assertIn("consulta su estado", self.invoke("AbrirBarreraIntent"))
        self.data.update_thing_shadow.assert_called_once()

    def test_no_user_id(self):
        request = event("AbrirBarreraIntent")
        del request["context"]["System"]["user"]
        response = lambda_function.lambda_handler(request, None)
        self.assertIn("validar", response["response"]["outputSpeech"]["text"])
        self.db.get_item.assert_not_called()

    def test_session_user_cannot_override_context_user(self):
        request = event("AbrirBarreraIntent")
        request["session"]["user"]["userId"] = OTHER_USER
        self.assertIn("validar", lambda_function.lambda_handler(request, None)["response"]["outputSpeech"]["text"])
        self.db.get_item.assert_not_called()

    def test_pairing_record_key_cannot_be_user(self):
        self.assertIn("identificar", self.invoke("AbrirBarreraIntent", user=pairing_key(CODE)))
        self.db.get_item.assert_not_called()

    def test_wrong_skill_or_missing_config(self):
        for skill in ("", "amzn1.ask.skill.other"):
            with patch.dict(os.environ, {"ALEXA_SKILL_ID": skill}):
                self.invoke("AbrirBarreraIntent")
        self.db.get_item.assert_not_called()

    def test_old_request_rejected(self):
        request = event("AbrirBarreraIntent")
        request["request"]["timestamp"] = (datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
        self.assertIn("validar", lambda_function.lambda_handler(request, None)["response"]["outputSpeech"]["text"])
        self.db.get_item.assert_not_called()

    def test_help_stop_cancel_fallback(self):
        for intent in ("AMAZON.HelpIntent", "AMAZON.StopIntent", "AMAZON.CancelIntent", "AMAZON.FallbackIntent", "UnknownIntent"):
            self.invoke(intent)
        self.db.get_item.assert_not_called()

    def test_session_ended(self):
        response = lambda_function.lambda_handler(event(kind="SessionEndedRequest"), None)
        self.assertNotIn("outputSpeech", response["response"])
        self.db.get_item.assert_not_called()

    def test_unexpected_error_is_safe(self):
        self.db.get_item.side_effect = RuntimeError("PRIVATE_VALUE_MUST_NOT_LEAK")
        self.assertIn("No pude", self.invoke())

    def test_endpoint_validation(self):
        self.assertEqual(validated_endpoint("example-ats.iot.us-east-1.amazonaws.com", "us-east-1"), "https://example-ats.iot.us-east-1.amazonaws.com")
        for endpoint in ("https://console.aws.amazon.com/iot", "evil.invalid", "https://example-ats.iot.us-east-1.amazonaws.com", "a.iot.eu-west-1.amazonaws.com"):
            with self.assertRaises(ConfigurationError):
                validated_endpoint(endpoint, "us-east-1")

    def test_lazy_client_reuse_and_retry_config(self):
        get_backend.cache_clear()
        clients = {"dynamodb": MagicMock(), "iot": MagicMock(), "iot-data": MagicMock()}
        clients["iot"].describe_endpoint.return_value = {"endpointAddress": "example-ats.iot.us-east-1.amazonaws.com"}
        with patch.dict(os.environ, {"IOT_DATA_ENDPOINT": ""}), patch("boto3.client", side_effect=lambda service, **kw: clients[service]) as factory:
            backend = get_backend()
            self.assertIs(get_backend(), backend)
            self.assertIs(backend.shadow.data_client_factory(), backend.shadow.data_client_factory())
            clients["iot"].describe_endpoint.assert_called_once_with(endpointType="iot:Data-ATS")
            self.assertEqual(factory.call_count, 3)
            for call in factory.call_args_list:
                self.assertEqual(call.kwargs["config"].retries["total_max_attempts"], 1)

    def test_configured_endpoint_skips_discovery(self):
        get_backend.cache_clear()
        with patch.dict(os.environ, {"IOT_DATA_ENDPOINT": "example-ats.iot.us-east-1.amazonaws.com"}), patch("boto3.client", return_value=self.iot):
            get_backend().shadow.data_client_factory()
            self.iot.describe_endpoint.assert_not_called()

    def test_missing_table_is_safe(self):
        get_backend.cache_clear()
        with patch.dict(os.environ, {"TABLE_NAME": ""}):
            with self.assertRaises(ConfigurationError):
                get_backend()


if __name__ == "__main__":
    unittest.main()
