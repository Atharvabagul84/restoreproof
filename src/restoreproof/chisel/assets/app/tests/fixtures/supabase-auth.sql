-- Test-only auth interface for the real PostgreSQL engine in PGlite.
-- This emulates database roles/auth.uid(), not the hosted Supabase Auth service.
create role anon nologin;
create role authenticated nologin;
create schema auth;
create table auth.users (
  id uuid primary key,
  email text not null,
  email_confirmed_at timestamptz
);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
create function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$$;
grant usage on schema public, auth to authenticated, anon;
grant execute on function auth.uid(), auth.jwt() to authenticated, anon;
