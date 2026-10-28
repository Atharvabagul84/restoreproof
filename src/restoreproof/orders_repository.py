"""Restricted SQL for the synthetic orders fixture in an owned lab database.

Queries connect as the application role over the container's Unix socket.
The trusted Docker adapter still possesses administrative access. This is a
local synthetic lab relying on container-local trust authentication, not a
production credential configuration or an arbitrary SQL sandbox.
"""
import json
from uuid import UUID


APP_ROLE = "restoreproof_orders_app"


def canonical_uuid(value):
    if not isinstance(value, str) or len(value) != 36 or str(UUID(value)) != value:
        raise ValueError("A canonical UUID is required.")
    return value


def quantity_value(value):
    if type(value) is not int or not 1 <= value <= 10000:
        raise ValueError("Quantity must be an integer between 1 and 10000.")
    return value


def _reject_constant(value):
    raise ValueError("Invalid JSON numeric constant.")


class OrdersRepository:
    def __init__(self, target):
        self.target = target

    def provision_role(self):
        """Provision access only: never create or repair restored schema/data/RLS."""
        self.target.execute("""
BEGIN;
SET LOCAL statement_timeout = 5000;
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'restoreproof_orders_app') THEN
        CREATE ROLE restoreproof_orders_app LOGIN NOSUPERUSER NOCREATEDB
            NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END $$;
REVOKE CREATE, TEMPORARY ON DATABASE restoreproof FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA orders_app TO restoreproof_orders_app;
GRANT SELECT, INSERT ON orders_app.orders TO restoreproof_orders_app;
COMMIT;
""")

    def _query(self, sql, tenant_id=None):
        tenant = "" if tenant_id is None else (
            "SET LOCAL restoreproof.tenant_id = '" + canonical_uuid(tenant_id) + "';\n")
        statement = "BEGIN;\nSET LOCAL statement_timeout = 5000;\n" + tenant + sql + ";\nCOMMIT;\n"
        raw = self.target._run(
            "exec", "-i", self.target._owned(), "psql", "-XqAt", "-v", "ON_ERROR_STOP=1",
            "-U", APP_ROLE, "-d", "restoreproof", input_data=statement.encode("utf-8"))
        return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)

    def get(self, tenant_id, order_id):
        order_id = canonical_uuid(order_id)
        return self._query(
            "SELECT COALESCE((SELECT json_build_object('id', id, 'quantity', quantity) "
            f"FROM orders_app.orders WHERE id = '{order_id}'), 'null'::json)", tenant_id)

    def create(self, tenant_id, order_id, quantity):
        tenant_id, order_id = canonical_uuid(tenant_id), canonical_uuid(order_id)
        quantity = quantity_value(quantity)
        return self._query(
            "WITH inserted AS (INSERT INTO orders_app.orders (id, tenant_id, quantity) "
            f"VALUES ('{order_id}', '{tenant_id}', {quantity}) RETURNING id, quantity) "
            "SELECT json_build_object('id', id, 'quantity', quantity) FROM inserted", tenant_id)

    def security_facts(self):
        return self._query("""
SELECT json_build_object(
    'role', current_user,
    'session_user', session_user,
    'superuser', (SELECT rolsuper FROM pg_roles WHERE rolname = current_user),
    'bypass_rls', (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user),
    'create_role', (SELECT rolcreaterole FROM pg_roles WHERE rolname = current_user),
    'create_database', (SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user),
    'rls_active', row_security_active('orders_app.orders'),
    'schema_create', has_schema_privilege(current_user, 'orders_app', 'CREATE'),
    'database_create', has_database_privilege(current_user, current_database(), 'CREATE'),
    'temporary_create', has_database_privilege(current_user, current_database(), 'TEMP'),
    'truncate', has_table_privilege(current_user, 'orders_app.orders', 'TRUNCATE'))
""")
