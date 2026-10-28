"""Restore evidence through real loopback HTTP and a restricted SQL role."""
import json
from pathlib import Path
import secrets
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4

from .orders_http import OrdersHTTPServer
from .orders_repository import OrdersRepository, canonical_uuid
from .orders_service import OrdersService

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
EXISTING_ORDER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FOREIGN_ORDER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
REQUIRED_APPLICATION_CHECKS = frozenset({
    "application-database-role", "application-read-existing-order", "application-read-second-tenant-order",
    "application-create-order", "application-read-persisted-order", "application-cross-tenant-denied",
    "application-missing-order", "application-unauthenticated-denied",
})
EXPECTED_SECURITY = {
    "role": "restoreproof_orders_app", "session_user": "restoreproof_orders_app",
    "superuser": False, "bypass_rls": False, "create_role": False, "create_database": False,
    "rls_active": True, "schema_create": False, "database_create": False,
    "temporary_create": False, "truncate": False,
}


def prepare_orders(target):
    """Seed a new source only. Never call this while validating a restored target."""
    target.execute((Path(__file__).with_name("fixtures") / "orders.sql").read_text(encoding="utf-8"))


def _request(base_url, method, path, token=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(base_url + path, data=data, headers=headers, method=method)
    # Always stay on loopback, regardless of host HTTP proxy configuration.
    opener = build_opener(ProxyHandler({}))
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        body = response.read(4097)
        if len(body) > 4096:
            raise ValueError("Application response exceeded the limit.")
        return response.status, json.loads(body)


def run_application_journey(target):
    """Return secret-free check results; bootstrap only missing role/grants."""
    checks = []
    repository = OrdersRepository(target)
    try:
        repository.provision_role()
        facts = repository.security_facts()
    except Exception as error:
        return [{"name": "application-bootstrap", "status": "INCOMPLETE",
                 "reason": "Application bootstrap could not complete (" + type(error).__name__ + ")."}]
    checks.append({"name": "application-database-role", "status": "PASS" if facts == EXPECTED_SECURITY else "FAIL",
                   "expected": EXPECTED_SECURITY, "actual": facts})
    if facts != EXPECTED_SECURITY:
        return checks
    token_a, token_b = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    service = OrdersService(repository, {token_a: TENANT_A, token_b: TENANT_B})

    def check(name, response, expected_status, expected_body=None):
        status, body = response
        passed = status == expected_status and (expected_body is None or body == expected_body)
        checks.append({"name": "application-" + name, "status": "PASS" if passed else "FAIL",
                       "expected_http_status": expected_status, "actual_http_status": status,
                       "response_matches": expected_body is None or body == expected_body})
        return passed

    try:
        with OrdersHTTPServer(service) as server:
            base = server.base_url
            check("read-existing-order", _request(base, "GET", "/orders/" + EXISTING_ORDER_ID, token_a),
                  200, {"id": EXISTING_ORDER_ID, "quantity": 7})
            check("read-second-tenant-order", _request(base, "GET", "/orders/" + FOREIGN_ORDER_ID, token_b),
                  200, {"id": FOREIGN_ORDER_ID, "quantity": 3})
            created = _request(base, "POST", "/orders", token_a, {"quantity": 11})
            valid_create = (isinstance(created[1], dict) and set(created[1]) == {"id", "quantity"}
                            and created[1]["quantity"] == 11)
            if valid_create:
                try:
                    canonical_uuid(created[1]["id"])
                except ValueError:
                    valid_create = False
            created_passed = check("create-order", created, 201)
            if not valid_create:
                checks[-1]["status"], checks[-1]["response_matches"] = "FAIL", False
            if created_passed and valid_create:
                check("read-persisted-order", _request(base, "GET", "/orders/" + created[1]["id"], token_a),
                      200, created[1])
            else:
                checks.append({"name": "application-read-persisted-order", "status": "FAIL",
                               "reason": "No valid created order was available for a separate read request."})
            not_found = {"error": "Order not found."}
            check("cross-tenant-denied", _request(base, "GET", "/orders/" + FOREIGN_ORDER_ID, token_a), 404, not_found)
            check("missing-order", _request(base, "GET", "/orders/" + str(uuid4()), token_a), 404, not_found)
            check("unauthenticated-denied", _request(base, "GET", "/orders/" + EXISTING_ORDER_ID), 401,
                  {"error": "Authentication required."})
    except Exception as error:
        checks.append({"name": "application-http-journey", "status": "INCOMPLETE",
                       "reason": "Application journey could not complete (" + type(error).__name__ + ")."})
    return checks
