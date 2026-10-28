-- Minimal standard Supabase JWT helpers required by Chisel's unchanged SQL.
-- Auth tables and migrations are created by genuine GoTrue, never by a fixture.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid;
$$;
CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$
  SELECT coalesce(nullif(current_setting('request.jwt.claim', true), ''),
    nullif(current_setting('request.jwt.claims', true), ''))::jsonb;
$$;
ALTER FUNCTION auth.uid() OWNER TO supabase_auth_admin;
ALTER FUNCTION auth.jwt() OWNER TO supabase_auth_admin;
GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.uid(), auth.jwt() TO anon, authenticated, service_role;
