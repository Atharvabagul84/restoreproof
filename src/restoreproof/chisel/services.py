"""Configuration for local-only, genuine application dependencies."""
PUBLISHABLE_KEY = 'sb_publishable_restoreproof_local_chisel_v03'
APP_ORIGIN = 'https://127.0.0.1:3443'


def configurations(auth_password, rest_password, jwt_secret, *, missing_config=False):
    auth = {
        'GOTRUE_API_HOST': '127.0.0.1', 'GOTRUE_API_PORT': '9999',
        'API_EXTERNAL_URL': 'http://127.0.0.1:8000/auth/v1',
        'GOTRUE_DB_DRIVER': 'postgres',
        'GOTRUE_DB_DATABASE_URL': f'postgres://supabase_auth_admin:{auth_password}@127.0.0.1:5432/restoreproof',
        'GOTRUE_SITE_URL': APP_ORIGIN, 'GOTRUE_JWT_SECRET': jwt_secret,
        'GOTRUE_JWT_ISSUER': 'http://127.0.0.1:8000/auth/v1',
        'GOTRUE_JWT_AUD': 'authenticated', 'GOTRUE_JWT_DEFAULT_GROUP_NAME': 'authenticated',
        'GOTRUE_JWT_ADMIN_ROLES': 'service_role', 'GOTRUE_JWT_EXP': '3600',
        'GOTRUE_EXTERNAL_EMAIL_ENABLED': 'true', 'GOTRUE_EXTERNAL_ANONYMOUS_USERS_ENABLED': 'false',
        'GOTRUE_DISABLE_SIGNUP': 'false', 'GOTRUE_MAILER_AUTOCONFIRM': 'false',
        'GOTRUE_SMTP_HOST': '127.0.0.1', 'GOTRUE_SMTP_PORT': '1025',
        'GOTRUE_SMTP_ADMIN_EMAIL': 'noreply@restoreproof.test', 'GOTRUE_SMTP_SENDER_NAME': 'RestoreProof lab',
        'GOTRUE_SMTP_MAX_FREQUENCY': '1s', 'GOTRUE_RATE_LIMIT_EMAIL_SENT': '1000',
        'GOTRUE_MAILER_TEMPLATES_CONFIRMATION': 'http://127.0.0.1:8000/templates/email',
        'GOTRUE_MAILER_TEMPLATES_MAGIC_LINK': 'http://127.0.0.1:8000/templates/email',
        'GOTRUE_LOG_LEVEL': 'error',
    }
    app = {'NODE_ENV': 'production', 'NEXT_TELEMETRY_DISABLED': '1',
           'NEXT_PUBLIC_SUPABASE_URL': 'http://127.0.0.1:8000',
           'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY': PUBLISHABLE_KEY}
    if not missing_config:
        app['CHISEL_APP_URL'] = APP_ORIGIN
    return {
        'mail': {'MP_SMTP_BIND_ADDR': '127.0.0.1:1025', 'MP_UI_BIND_ADDR': '127.0.0.1:8025',
                 'MP_DATABASE': '/tmp/mailpit.db', 'MP_MAX_MESSAGES': '50', 'MP_DISABLE_VERSION_CHECK': 'true'},
        'gateway': {}, 'auth': auth,
        'rest': {'PGRST_DB_URI': f'postgres://authenticator:{rest_password}@127.0.0.1:5432/restoreproof',
                 'PGRST_DB_SCHEMAS': 'public', 'PGRST_DB_ANON_ROLE': 'anon', 'PGRST_JWT_SECRET': jwt_secret,
                 'PGRST_SERVER_HOST': '127.0.0.1', 'PGRST_SERVER_PORT': '3000',
                 'PGRST_LOG_LEVEL': 'error', 'PGRST_DB_POOL': '5'},
        'app': app,
    }
