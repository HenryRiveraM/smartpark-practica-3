"""Administracion aislada: clientes dobles, sin ASK ni acceso real a AWS."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ReadTimeoutError

import admin_lambda_function
from administration.pairing_service import PairingAdminService
from administration.runtime import get_admin_service
from fakes import AtomicDynamo, error
from services.errors import UserError
from services.pairing_policy import pairing_window_key
from services.validation import pairing_key

USER = "amzn1.ask.account.ADMIN_TEST_USER"
THING = "device-admin-test"


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.store = AtomicDynamo()
        self.db = MagicMock(wraps=self.store)
        self.iot = MagicMock()
        self.now = 1000
        self.service = PairingAdminService(self.db, self.iot, "SmartParkBindings", clock=lambda: self.now)
        self.no_aws = patch("boto3.client", side_effect=AssertionError("No real AWS allowed"))
        self.no_aws.start()
        self.addCleanup(self.no_aws.stop)
        self.addCleanup(get_admin_service.cache_clear)

    def test_secure_random_bounds_and_hash_only(self):
        for random_value, expected in ((0, "1000"), (8999, "9999")):
            self.store.items.clear()
            with patch("administration.pairing_service.secrets.randbelow", return_value=random_value) as random:
                result = self.service.generate(USER, THING)
            random.assert_called_once_with(9000)
            self.assertEqual(result, {"codigo": expected, "thingName": THING, "expiresInSeconds": 300})
            item = self.store.items[pairing_key(expected)]
            self.assertEqual(item["expiresAt"], {"N": "1300"})
            self.assertEqual(item["allowedUserId"], {"S": USER})
            self.assertNotIn('"S": "'+expected+'"', json.dumps(self.store.items))
            self.assertEqual(self.store.items[pairing_window_key(USER)]["remainingAttempts"], {"N": "3"})
        self.iot.describe_thing.assert_called_with(thingName=THING)

    def test_existing_thing_required(self):
        self.iot.describe_thing.side_effect = error("ResourceNotFoundException")
        with self.assertRaises(UserError):
            self.service.generate(USER, THING)
        self.db.transact_write_items.assert_not_called()

    def test_does_not_reset_active_window(self):
        self.service.generate(USER, THING)
        old = self.store.items[pairing_window_key(USER)].copy()
        with self.assertRaises(UserError):
            self.service.generate(USER, "another-thing")
        self.assertEqual(self.store.items[pairing_window_key(USER)], old)

    def test_consumed_window_still_blocks_regeneration(self):
        self.service.generate(USER, THING)
        self.store.items[pairing_window_key(USER)]["status"] = {"S": "consumed"}
        self.store.items[pairing_window_key(USER)]["remainingAttempts"] = {"N": "0"}
        with self.assertRaises(UserError):
            self.service.generate(USER, THING)

    def test_expired_window_can_be_replaced(self):
        self.service.generate(USER, THING)
        self.now = 1300
        result = self.service.generate(USER, THING)
        self.assertEqual(self.store.items[pairing_key(result["codigo"])]["expiresAt"], {"N": "1600"})

    def test_parallel_generation_returns_only_one_pin(self):
        def generate(_):
            try:
                return self.service.generate(USER, THING)
            except UserError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(generate, range(12)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(sum(key.startswith("PAIR#") for key in self.store.items), 1)

    def test_collision_retries_only_pin_and_rolls_back_window(self):
        with patch("administration.pairing_service.secrets.randbelow", return_value=0):
            self.service.generate("amzn1.ask.account.ANOTHER_USER", THING)
        self.db.reset_mock()
        with patch("administration.pairing_service.secrets.randbelow", side_effect=[0, 1]):
            result = self.service.generate(USER, THING)
        self.assertEqual(result["codigo"], "1001")
        self.assertEqual(self.db.transact_write_items.call_count, 2)
        self.assertEqual(self.store.items[pairing_key("1000")]["allowedUserId"]["S"], "amzn1.ask.account.ANOTHER_USER")

    def test_collision_attempts_bounded(self):
        with patch("administration.pairing_service.secrets.randbelow", return_value=0):
            self.service.generate("amzn1.ask.account.ANOTHER_USER", THING)
            self.db.reset_mock()
            with self.assertRaises(UserError):
                self.service.generate(USER, THING)
        self.assertEqual(self.db.transact_write_items.call_count, 3)
        self.assertNotIn(pairing_window_key(USER), self.store.items)

    def test_network_failure_not_retried(self):
        self.db.transact_write_items.side_effect = ReadTimeoutError(endpoint_url="https://test.invalid")
        with self.assertRaises(UserError):
            self.service.generate(USER, THING)
        self.db.transact_write_items.assert_called_once()

    def test_unknown_transaction_cancellation_fails_closed(self):
        self.db.transact_write_items.side_effect = error("TransactionCanceledException")
        with self.assertRaises(UserError):
            self.service.generate(USER, THING)
        self.db.transact_write_items.assert_called_once()

    def test_handler_success_does_not_log_pin_or_user(self):
        with patch("admin_lambda_function.get_admin_service", return_value=self.service), self.assertNoLogs("smartpark.admin", level="DEBUG"):
            result = admin_lambda_function.lambda_handler({"allowedUserId": USER, "thingName": THING}, None)
        self.assertRegex(result["codigo"], r"^[1-9][0-9]{3}$")

    def test_handler_aws_error_sanitized(self):
        self.iot.describe_thing.side_effect = error("AccessDeniedException")
        with patch("admin_lambda_function.get_admin_service", return_value=self.service), self.assertLogs("smartpark.admin", level="WARNING") as logs:
            result = admin_lambda_function.lambda_handler({"allowedUserId": USER, "thingName": THING}, None)
        self.assertNotIn(USER, str(result))
        self.assertNotIn("PRIVATE_VALUE", str(result))
        self.assertEqual(logs.output, ["WARNING:smartpark.admin:generation_failed type=ServiceError"])

    def test_admin_rejects_alexa_envelopes_before_creating_clients(self):
        events = ({"version": "1.0", "request": {"type": "LaunchRequest"}},
                  {"allowedUserId": USER, "thingName": THING, "request": {"type": "IntentRequest"}},
                  {"allowedUserId": USER, "thingName": THING, "admin": True},
                  {"allowedUserId": USER, "thingName": THING, "expiresInSeconds": 3600})
        with patch("admin_lambda_function.get_admin_service") as runtime:
            for event in events:
                self.assertIn("error", admin_lambda_function.lambda_handler(event, None))
            runtime.assert_not_called()

    def test_admin_rejects_invalid_user_and_thing(self):
        with patch("admin_lambda_function.get_admin_service") as runtime:
            for user, thing in (("PAIR#fake", THING), (USER, "../../thing")):
                self.assertIn("error", admin_lambda_function.lambda_handler({"allowedUserId": user, "thingName": thing}, None))
            runtime.assert_not_called()

    def test_clients_reused_and_retries_disabled(self):
        get_admin_service.cache_clear()
        with patch.dict(os.environ, {"TABLE_NAME": "SmartParkBindings", "AWS_REGION": "us-east-1"}), patch("boto3.client", return_value=self.iot) as factory:
            self.assertIs(get_admin_service(), get_admin_service())
            self.assertEqual(factory.call_count, 2)
            for call in factory.call_args_list:
                self.assertEqual(call.kwargs["config"].retries["total_max_attempts"], 1)
                self.assertEqual(call.kwargs["config"].connect_timeout, 0.5)
