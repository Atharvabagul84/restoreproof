"""Opt-in real restore → restricted database role → loopback HTTP journey."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid


@unittest.skipUnless(os.environ.get("RESTOREPROOF_INTEGRATION") == "1", "requires explicitly enabled Docker")
class ApplicationIntegrationTests(unittest.TestCase):
    def setUp(self):
        from restoreproof.application_journey import prepare_orders
        from restoreproof.contract import APPROVED_IMAGE
        from restoreproof.docker_postgres import DockerPostgres
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        archive = Path(self.temporary.name) / "orders.dump"
        source = DockerPostgres(APPROVED_IMAGE, uuid.uuid4().hex)
        try:
            source.create()
            prepare_orders(source)
            source.dump(archive)
        finally:
            self.assertEqual(source.cleanup()["status"], "PASS")
        self.target = DockerPostgres(APPROVED_IMAGE, uuid.uuid4().hex)
        self.addCleanup(self.cleanup_target)
        self.target.create()
        self.target.restore(archive, hashlib.sha256(archive.read_bytes()).hexdigest())

    def cleanup_target(self):
        self.assertEqual(self.target.cleanup()["status"], "PASS")

    def test_restored_orders_pass_actual_http_journey(self):
        from restoreproof.application_journey import run_application_journey
        checks = run_application_journey(self.target)
        self.assertTrue(all(check["status"] == "PASS" for check in checks), checks)

    def test_application_role_cannot_ddl_or_bypass_rls(self):
        from restoreproof.orders_repository import OrdersRepository
        from restoreproof.application_journey import TENANT_A, FOREIGN_ORDER_ID
        from restoreproof.process import ProcessError
        repository = OrdersRepository(self.target)
        repository.provision_role()
        self.assertIsNone(repository.get(TENANT_A, FOREIGN_ORDER_ID))
        self.assertEqual(repository._query("RESET ROLE; SELECT to_json(current_user)"), "restoreproof_orders_app")
        for statement in ["CREATE TABLE orders_app.forbidden(id int)",
                          "ALTER TABLE orders_app.orders DISABLE ROW LEVEL SECURITY",
                          "SET LOCAL row_security=off; SELECT count(*) FROM orders_app.orders"]:
            with self.subTest(statement=statement), self.assertRaises(ProcessError):
                repository._query(statement)

    def test_sql_can_pass_while_revoked_write_privilege_fails_http(self):
        from restoreproof.orders_repository import OrdersRepository
        from restoreproof.application_journey import run_application_journey
        self.assertEqual(self.target.query("SELECT count(*)::int FROM orders_app.orders"), 2)
        original = OrdersRepository.provision_role
        def read_only(repository):
            original(repository)
            self.target.execute("REVOKE INSERT ON orders_app.orders FROM restoreproof_orders_app;")
        with patch.object(OrdersRepository, "provision_role", read_only):
            checks = run_application_journey(self.target)
        self.assertEqual(next(c for c in checks if c["name"] == "application-create-order")["status"], "FAIL")

    def test_missing_restored_table_is_not_repaired_by_application_setup(self):
        from restoreproof.application_journey import run_application_journey
        self.target.execute("DROP TABLE orders_app.orders;")
        self.assertEqual(self.target.query("SELECT 1"), 1)
        checks = run_application_journey(self.target)
        self.assertEqual(checks[0]["status"], "INCOMPLETE")
        self.assertTrue(self.target.query("SELECT to_json(to_regclass('orders_app.orders') IS NULL)"))


if __name__ == "__main__":
    unittest.main()
