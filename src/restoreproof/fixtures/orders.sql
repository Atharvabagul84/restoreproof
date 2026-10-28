-- Synthetic restore fixture. Role/grants are deliberately provisioned after restore.
CREATE SCHEMA orders_app;
REVOKE ALL ON SCHEMA orders_app FROM PUBLIC;
CREATE TABLE orders_app.tenants (id uuid PRIMARY KEY);
CREATE TABLE orders_app.orders (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES orders_app.tenants(id),
    quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 10000)
);
REVOKE ALL ON ALL TABLES IN SCHEMA orders_app FROM PUBLIC;
INSERT INTO orders_app.tenants VALUES
    ('11111111-1111-1111-1111-111111111111'),
    ('22222222-2222-2222-2222-222222222222');
INSERT INTO orders_app.orders VALUES
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111', 7),
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '22222222-2222-2222-2222-222222222222', 3);
ALTER TABLE orders_app.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders_app.orders FORCE ROW LEVEL SECURITY;
-- PUBLIC names policy applicability, not table access. No PUBLIC grants exist.
CREATE POLICY tenant_orders ON orders_app.orders TO PUBLIC
    USING (tenant_id = nullif(current_setting('restoreproof.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('restoreproof.tenant_id', true), '')::uuid);
