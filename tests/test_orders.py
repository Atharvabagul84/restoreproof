"""Domain and real loopback HTTP tests; Docker remains a separate boundary."""
import json
import secrets
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from uuid import uuid4

from restoreproof.orders_repository import OrdersRepository
from restoreproof.orders_service import OrdersService, OrdersError
from restoreproof.orders_http import OrdersHTTPServer
from restoreproof.application_journey import (
    EXISTING_ORDER_ID, FOREIGN_ORDER_ID, TENANT_A, TENANT_B,
    REQUIRED_APPLICATION_CHECKS, run_application_journey,
)


class MemoryOrders:
    def __init__(self, *, readonly=False, missing=False):
        self.rows = {(TENANT_A, EXISTING_ORDER_ID): {"id": EXISTING_ORDER_ID, "quantity": 7},
                     (TENANT_B, FOREIGN_ORDER_ID): {"id": FOREIGN_ORDER_ID, "quantity": 3}}
        self.readonly, self.missing = readonly, missing

    def provision_role(self):
        if self.missing:
            raise RuntimeError("missing table")

    def security_facts(self):
        return {"role": "restoreproof_orders_app", "session_user": "restoreproof_orders_app",
                "superuser": False, "bypass_rls": False, "create_role": False, "create_database": False,
                "rls_active": True, "schema_create": False, "database_create": False,
                "temporary_create": False, "truncate": False}

    def get(self, tenant_id, order_id):
        if self.missing:
            raise RuntimeError("missing table")
        return self.rows.get((tenant_id, order_id))

    def create(self, tenant_id, order_id, quantity):
        if self.readonly:
            raise RuntimeError("private-provider-password")
        row = {"id": order_id, "quantity": quantity}
        self.rows[(tenant_id, order_id)] = row
        return row


def request(base, method, path, token=None, body=None, raw=None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


class OrdersTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryOrders()
        self.token_a, self.token_b = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.service = OrdersService(self.repository, {self.token_a: TENANT_A, self.token_b: TENANT_B})

    def test_service_authentication_precedes_repository_access(self):
        with self.assertRaises(OrdersError) as caught:
            self.service.get(None, EXISTING_ORDER_ID)
        self.assertEqual(caught.exception.status, 401)

    def test_non_ascii_authorization_is_unauthenticated(self):
        with self.assertRaises(OrdersError) as caught:
            self.service.get("Bearer \u00e9", EXISTING_ORDER_ID)
        self.assertEqual(caught.exception.status, 401)

    def test_service_rejects_caller_selected_tenant_and_invalid_quantities(self):
        for body in [{"quantity": 1, "tenant_id": TENANT_B}, {"quantity": True},
                     {"quantity": 0}, {"quantity": 10001}, {"quantity": "1"}, [], {}]:
            with self.subTest(body=body), self.assertRaises(OrdersError) as caught:
                self.service.create("Bearer " + self.token_a, body)
            self.assertEqual(caught.exception.status, 400)

    def test_http_reads_creates_and_reads_committed_order_on_new_request(self):
        with OrdersHTTPServer(self.service) as server:
            self.assertTrue(server.base_url.startswith("http://127.0.0.1:"))
            status, existing = request(server.base_url, "GET", "/orders/" + EXISTING_ORDER_ID, self.token_a)
            self.assertEqual((status, existing), (200, {"id": EXISTING_ORDER_ID, "quantity": 7}))
            status, created = request(server.base_url, "POST", "/orders", self.token_a, {"quantity": 11})
            self.assertEqual(status, 201)
            self.assertEqual(request(server.base_url, "GET", "/orders/" + created["id"], self.token_a), (200, created))

    def test_http_missing_and_foreign_orders_are_indistinguishable(self):
        with OrdersHTTPServer(self.service) as server:
            foreign = request(server.base_url, "GET", "/orders/" + FOREIGN_ORDER_ID, self.token_a)
            missing = request(server.base_url, "GET", "/orders/" + str(uuid4()), self.token_a)
            self.assertEqual(foreign, missing)
            self.assertEqual(foreign[0], 404)
            self.assertEqual(request(server.base_url, "GET", "/orders/" + FOREIGN_ORDER_ID, self.token_b)[0], 200)

    def test_http_unauthenticated_and_invalid_token_are_rejected(self):
        with OrdersHTTPServer(self.service) as server:
            for token in [None, "not-a-token"]:
                self.assertEqual(request(server.base_url, "GET", "/orders/" + EXISTING_ORDER_ID, token)[0], 401)

    def test_http_rejects_oversized_malformed_and_tenant_override_bodies(self):
        with OrdersHTTPServer(self.service) as server:
            for body in [b"x" * 1025, b"{", b'{"quantity":1,"tenant_id":"foreign"}']:
                status, _ = request(server.base_url, "POST", "/orders", self.token_a, raw=body)
                self.assertIn(status, [400, 413])

    def test_http_provider_failure_is_sanitized(self):
        self.repository.readonly = True
        with OrdersHTTPServer(self.service) as server:
            status, body = request(server.base_url, "POST", "/orders", self.token_a, {"quantity": 1})
            self.assertEqual(status, 500)
            self.assertNotIn("private-provider-password", json.dumps(body))

    def test_repository_rejects_sql_injection_before_calling_database(self):
        class UnusedTarget:
            def _sql(self, sql):
                raise AssertionError("invalid values reached SQL")
        repository = OrdersRepository(UnusedTarget())
        for tenant, order in [(TENANT_A, "'; DROP TABLE orders;--"), ("x' OR true--", EXISTING_ORDER_ID)]:
            with self.assertRaises(ValueError):
                repository.get(tenant, order)

    def test_repository_connects_as_restricted_role_without_application_tenant_filter(self):
        class Target:
            sql = ""
            args = ()
            def _owned(self):
                return "owned-container"
            def _run(self, *args, **kwargs):
                self.args = args
                self.sql = kwargs["input_data"].decode()
                return b"null\n"
        target = Target()
        self.assertIsNone(OrdersRepository(target).get(TENANT_A, EXISTING_ORDER_ID))
        self.assertEqual(target.args[target.args.index("-U") + 1], "restoreproof_orders_app")
        self.assertIn("owned-container", target.args)
        self.assertNotIn("SET LOCAL ROLE", target.sql)
        self.assertIn("restoreproof.tenant_id", target.sql)
        self.assertNotIn("WHERE tenant_id", target.sql)
        self.assertIn("statement_timeout", target.sql)

    def test_role_setup_never_repairs_schema_policies_or_data(self):
        class Target:
            sql = ""
            def execute(self, sql):
                self.sql = sql
        target = Target()
        OrdersRepository(target).provision_role()
        self.assertIn("CREATE ROLE restoreproof_orders_app LOGIN", target.sql)
        for forbidden in ["CREATE TABLE", "CREATE POLICY", "ENABLE ROW LEVEL SECURITY", "INSERT INTO"]:
            self.assertNotIn(forbidden, target.sql.upper())

    def test_complete_journey_produces_secret_free_observable_checks(self):
        with patch("restoreproof.application_journey.OrdersRepository", return_value=self.repository):
            checks = run_application_journey(object())
        self.assertEqual({check["name"] for check in checks}, REQUIRED_APPLICATION_CHECKS)
        self.assertTrue(all(check["status"] == "PASS" for check in checks), checks)
        self.assertTrue(any(check["name"] == "application-create-order" for check in checks))
        self.assertNotIn("Bearer", json.dumps(checks))

    def test_readonly_application_fails_journey_even_when_database_read_is_healthy(self):
        self.repository.readonly = True
        self.assertEqual(self.repository.get(TENANT_A, EXISTING_ORDER_ID)["quantity"], 7)
        with patch("restoreproof.application_journey.OrdersRepository", return_value=self.repository):
            checks = run_application_journey(object())
        create = next(check for check in checks if check["name"] == "application-create-order")
        self.assertEqual(create["status"], "FAIL")
        self.assertEqual(create["actual_http_status"], 500)

    def test_missing_table_is_reported_without_seeding_or_repair(self):
        with patch("restoreproof.application_journey.OrdersRepository", return_value=MemoryOrders(missing=True)):
            checks = run_application_journey(object())
        self.assertEqual(checks[0]["name"], "application-bootstrap")
        self.assertEqual(checks[0]["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
