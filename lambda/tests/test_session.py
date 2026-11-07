"""Control de sesion ASK sin cambiar servicios ni generar llamadas AWS extra."""
import json
import unittest

from ask_sdk_core.serialize import DefaultSerializer
from ask_sdk_model.response_envelope import ResponseEnvelope
from botocore.exceptions import ReadTimeoutError

import lambda_function
import test_backend as fixtures


class SessionTests(unittest.TestCase):
    # Reutilizar fixtures, sin heredar ni repetir la suite del backend.
    bind = fixtures.BackendTests.bind
    report = fixtures.BackendTests.report

    def setUp(self):
        fixtures.BackendTests.setUp(self)
        self.bind()

    def response(self, intent=None, *, new=False, attributes=None, kind=None, index=1):
        request = fixtures.event(intent, kind=kind)
        request["session"]["new"] = new
        request["session"]["attributes"] = attributes or {}
        request["request"]["requestId"] = f"amzn1.echo-api.request.session-{index}"
        result = lambda_function.lambda_handler(request, None)
        envelope = DefaultSerializer().deserialize(json.dumps(result), ResponseEnvelope)
        self.assertIsNotNone(envelope.response)
        return result

    def assert_open(self, result):
        response = result["response"]
        self.assertIs(response["shouldEndSession"], False)
        reprompt = response["reprompt"]["outputSpeech"]
        text = reprompt.get("ssml", reprompt.get("text", ""))
        self.assertIn("salir", text)
        self.assertTrue(text.strip())

    def assert_closed(self, result):
        self.assertIs(result["response"]["shouldEndSession"], True)
        self.assertNotIn("reprompt", result["response"])

    def test_five_successful_intents_keep_session_and_same_aws_call_counts(self):
        for intent in ("AbrirBarreraIntent", "CerrarBarreraIntent", "EstadoBarreraIntent", "ConsultarDistanciaIntent", "ConsultarVehiculoIntent"):
            with self.subTest(intent=intent):
                self.db.get_item.reset_mock()
                self.data.get_thing_shadow.reset_mock()
                self.data.update_thing_shadow.reset_mock()
                result = self.response(intent)
                self.assert_open(result)
                self.db.get_item.assert_called_once()
                if intent in {"AbrirBarreraIntent", "CerrarBarreraIntent"}:
                    self.data.update_thing_shadow.assert_called_once()
                    self.data.get_thing_shadow.assert_not_called()
                    self.assertIn("Solicité", result["response"]["outputSpeech"]["ssml"])
                else:
                    self.data.get_thing_shadow.assert_called_once()
                    self.data.update_thing_shadow.assert_not_called()
        self.db.update_item.assert_not_called()
        self.db.transact_write_items.assert_not_called()
        self.iot.describe_thing.assert_not_called()

    def test_launch_open_state_close_stop_with_same_session(self):
        attributes = {}
        for index, intent in enumerate((None, "AbrirBarreraIntent", "EstadoBarreraIntent", "CerrarBarreraIntent", "AMAZON.StopIntent")):
            result = self.response(intent, new=index == 0, attributes=attributes, index=index)
            if intent == "AMAZON.StopIntent":
                self.assert_closed(result)
            else:
                self.assert_open(result)
            attributes = result.get("sessionAttributes", {})
        self.assertEqual(self.db.get_item.call_count, 4)
        self.assertEqual(self.data.update_thing_shadow.call_count, 2)
        self.assertEqual(self.data.get_thing_shadow.call_count, 1)

    def test_stop_and_cancel_close_without_aws_calls(self):
        for intent in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
            with self.subTest(intent=intent):
                self.assert_closed(self.response(intent))
        self.db.get_item.assert_not_called()
        self.factory.assert_not_called()

    def test_session_ended_never_reopens_or_speaks(self):
        for reason in ("USER_INITIATED", "EXCEEDED_MAX_REPROMPTS", "ERROR"):
            request = fixtures.event(kind="SessionEndedRequest")
            request["request"]["reason"] = reason
            result = lambda_function.lambda_handler(request, None)
            self.assertIsNot(result["response"].get("shouldEndSession"), False)
            self.assertNotIn("reprompt", result["response"])
            self.assertNotIn("outputSpeech", result["response"])
        self.db.get_item.assert_not_called()
        self.factory.assert_not_called()

    def test_help_and_fallback_are_clear_and_do_not_call_aws(self):
        for intent in ("AMAZON.HelpIntent", "AMAZON.FallbackIntent", "UnknownIntent"):
            result = self.response(intent)
            self.assert_open(result)
            text = result["response"]["outputSpeech"]["ssml"]
            for command in ("abrir", "cerrar", "consultar estado", "consultar distancia", "salir"):
                self.assertIn(command, text)
        self.db.get_item.assert_not_called()
        self.factory.assert_not_called()

    def test_timeout_after_physical_request_closes_without_inviting_repetition(self):
        self.data.update_thing_shadow.side_effect = ReadTimeoutError(endpoint_url="https://test.invalid")
        result = self.response("AbrirBarreraIntent")
        self.assert_closed(result)
        self.assertIn("consulta su estado antes de repetir", result["response"]["outputSpeech"]["ssml"])
        self.data.update_thing_shadow.assert_called_once()
        self.data.get_thing_shadow.assert_not_called()

    def test_stale_or_invalid_data_closes_without_reprompt(self):
        self.report(age=181)
        self.assert_closed(self.response("EstadoBarreraIntent"))
        self.report(value=None)
        self.assert_closed(self.response("ConsultarDistanciaIntent"))
        self.report(presence=None)
        self.assert_closed(self.response("ConsultarVehiculoIntent"))

    def test_unbound_user_error_closes_without_physical_action(self):
        del self.items[fixtures.USER]
        self.assert_closed(self.response("CerrarBarreraIntent"))
        self.factory.assert_not_called()
