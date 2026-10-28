"""Disposable PostgreSQL with explicit Supabase roles and preserved restore ACLs."""
import re
from .assets import ASSETS
from ..docker_postgres import DockerPostgres


class ChiselPostgres(DockerPostgres):
    restore_options = ()

    def provision_roles(self, auth_password, rest_password):
        # Generated hex secrets only; no supplied identifiers or SQL interpolation.
        if not all(re.fullmatch(r'[0-9a-f]{64}', value) for value in (auth_password, rest_password)):
            raise ValueError('Expected generated database credentials.')
        self.execute(f"""
CREATE ROLE anon NOLOGIN NOINHERIT;
CREATE ROLE authenticated NOLOGIN NOINHERIT;
CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
CREATE ROLE authenticator LOGIN NOINHERIT PASSWORD '{rest_password}';
CREATE ROLE supabase_auth_admin LOGIN NOINHERIT CREATEROLE PASSWORD '{auth_password}';
GRANT anon, authenticated, service_role TO authenticator;
GRANT CONNECT ON DATABASE restoreproof TO authenticator, supabase_auth_admin;
ALTER ROLE supabase_auth_admin SET search_path TO auth, public, extensions;
""")

    def initialize_source(self):
        self.execute('CREATE SCHEMA auth AUTHORIZATION supabase_auth_admin;')

    def install_source_app(self):
        self.execute((ASSETS / 'auth-functions.sql').read_text(encoding='utf-8'))
        for migration in sorted((ASSETS / 'app/supabase/migrations').glob('*.sql')):
            self.execute(migration.read_text(encoding='utf-8'))
