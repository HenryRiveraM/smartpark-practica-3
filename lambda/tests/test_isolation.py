"""Integracion local entre ambos servicios; no se incluye en ninguno de los ZIP."""
import unittest
from unittest.mock import MagicMock, patch

import admin_lambda_function
import lambda_function
from administration.pairing_service import PairingAdminService
from fakes import AtomicDynamo
from services.dynamodb_service import DynamoDBService
from services.errors import UserError
from services.pairing_policy import pairing_window_key
from services.validation import pairing_key
from test_backend import event, USER, SKILL


class IsolationTests(unittest.TestCase):
    def test_generated_pin_can_bind_once_and_cannot_rearm_early(self):
        store = AtomicDynamo()
        clock = lambda: 1000
        admin = PairingAdminService(store, MagicMock(), "SmartParkBindings", clock=clock)
        backend = DynamoDBService(store, "SmartParkBindings", clock=clock)
        result = admin.generate(USER, "iot-integration-test")
        authorization = backend.authorize_code(USER, result["codigo"])
        backend.save_binding(USER, authorization, None)
        self.assertEqual(backend.get_binding(USER).thing_name, result["thingName"])
        self.assertNotIn(pairing_key(result["codigo"]), store.items)
        self.assertEqual(store.items[pairing_window_key(USER)]["status"]["S"], "consumed")
        backend.delete_binding(USER)
        with self.assertRaises(UserError):
            backend.authorize_code(USER, result["codigo"])
        with self.assertRaises(UserError):
            admin.generate(USER, "iot-integration-test")

    def test_alexa_cannot_route_admin_json_fields(self):
        with patch.dict("os.environ", {"ALEXA_SKILL_ID": SKILL}), patch("boto3.client", side_effect=AssertionError("No AWS allowed")), patch("admin_lambda_function.get_admin_service") as admin:
            payload = {"admin": True, "allowedUserId": USER, "thingName": "victim"}
            self.assertNotIn("codigo", lambda_function.lambda_handler(payload, None))
            payload = event("GenerarPinIntent")
            payload.update({"admin": True, "allowedUserId": USER, "thingName": "victim"})
            self.assertNotIn("codigo", lambda_function.lambda_handler(payload, None))
            admin.assert_not_called()
