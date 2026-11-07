"""PIN y contador publico: pruebas reales de concurrencia sobre un doble atomico."""
from concurrent.futures import ThreadPoolExecutor
import copy
import time
import unittest
from unittest.mock import MagicMock

from fakes import AtomicDynamo
from services.dynamodb_service import DynamoDBService
from services.errors import UserError
from services.pairing_policy import pairing_window_key
from services.validation import pairing_key

USER = "amzn1.ask.account.PIN_USER"
CODE = "5831"
THING = "device-pin-test"


def seed(store):
    expiry = str(int(time.time())+300)
    store.items[pairing_key(CODE)] = {
        "userId": {"S": pairing_key(CODE)}, "recordType": {"S": "pairing"},
        "thingName": {"S": THING}, "allowedUserId": {"S": USER},
        "expiresAt": {"N": expiry}, "generation": {"S": "generation-test"},
    }
    store.items[pairing_window_key(USER)] = {
        "userId": {"S": pairing_window_key(USER)}, "recordType": {"S": "pairing_window"},
        "thingName": {"S": THING}, "pairKey": {"S": pairing_key(CODE)},
        "expiresAt": {"N": expiry}, "generation": {"S": "generation-test"},
        "remainingAttempts": {"N": "3"}, "status": {"S": "active"},
    }


class PinPublicTests(unittest.TestCase):
    def setUp(self):
        self.store = AtomicDynamo()
        seed(self.store)
        self.service = DynamoDBService(self.store, "SmartParkBindings")

    def test_format(self):
        for pin in ("1000", "9999", "5 8 3 1", " 5831 ", "5\t831"):
            self.assertTrue(pairing_key(pin).startswith("PAIR#"))
        self.assertEqual(pairing_key("5 8 3 1"), pairing_key(CODE))
        for pin in ("0000", "0999", "999", "10000", "abcd", "58a1", "58-31", "58.31", "５８３１", "5\n831", None, 5831, "123456789012"):
            with self.subTest(pin=pin), self.assertRaises(UserError):
                pairing_key(pin)

    def test_wrong_pin_consumes_an_attempt_without_reading_pair(self):
        client = MagicMock(wraps=self.store)
        service = DynamoDBService(client, "SmartParkBindings")
        with self.assertRaises(UserError):
            service.authorize_code(USER, "5832")
        client.get_item.assert_not_called()
        self.assertEqual(self.store.reservations, 1)
        self.assertEqual(self.store.items[pairing_window_key(USER)]["remainingAttempts"]["N"], "2")

    def test_parallel_guesses_never_exceed_three(self):
        def attempt(_):
            try:
                self.service.authorize_code(USER, "5832")
            except UserError:
                return
            self.fail("Wrong PIN authorized")
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(attempt, range(30)))
        self.assertEqual(self.store.reservations, 3)
        with self.assertRaises(UserError):
            self.service.authorize_code(USER, CODE)
        self.assertIn(pairing_key(CODE), self.store.items)

    def test_last_attempt_can_be_correct(self):
        for _ in range(2):
            with self.assertRaises(UserError):
                self.service.authorize_code(USER, "5832")
        authorization = self.service.authorize_code(USER, CODE)
        self.service.save_binding(USER, authorization, None)
        self.assertNotIn(pairing_key(CODE), self.store.items)
        self.assertEqual(self.store.items[pairing_window_key(USER)]["status"]["S"], "consumed")

    def test_parallel_correct_consumption_succeeds_once(self):
        authorizations = [self.service.authorize_code(USER, CODE) for _ in range(3)]
        def consume(auth):
            try:
                self.service.save_binding(USER, auth, None)
                return True
            except UserError:
                return False
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(sum(pool.map(consume, authorizations)), 1)
        self.assertNotIn(pairing_key(CODE), self.store.items)
        with self.assertRaises(UserError):
            self.service.authorize_code(USER, CODE)

    def test_counter_survives_new_service_instance(self):
        for _ in range(3):
            with self.assertRaises(UserError):
                self.service.authorize_code(USER, "5832")
        restarted = DynamoDBService(self.store, "SmartParkBindings")
        with self.assertRaises(UserError):
            restarted.authorize_code(USER, CODE)

    def test_new_generation_invalidates_reserved_authorization(self):
        authorization = self.service.authorize_code(USER, CODE)
        original = copy.deepcopy(self.store.items)
        self.store.items[pairing_window_key(USER)]["generation"] = {"S": "new-generation"}
        with self.assertRaises(UserError):
            self.service.save_binding(USER, authorization, None)
        self.assertEqual(self.store.items[pairing_key(CODE)], original[pairing_key(CODE)])
        self.assertNotIn(USER, self.store.items)
