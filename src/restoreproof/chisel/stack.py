"""Bounded, owned service lifecycle. No published ports, mounts or egress."""
import json
import re
import secrets

from .database import ChiselPostgres
from .resources import COMPONENTS, COMPONENT_LABEL, RUN_LABEL, validate_owned, isolation_evidence
from .services import configurations


class ChiselStack:
    def __init__(self, run_id, images, *, journal=lambda: None):
        self.db = ChiselPostgres(images['database'], run_id, timeout_seconds=90)
        self.run_id, self.images, self.journal = run_id, images, journal
        self.ids, self.attempted = {}, set()
        self.isolation = {}
        self.recovery = False
        self.auth_password, self.rest_password, self.jwt_secret = (secrets.token_hex(32) for _ in range(3))

    def create_database(self, *, source=False):
        self.db.create()
        self.isolation['database'] = isolation_evidence(self.db._inspect_owned(self.db.container_id), 'database', self.db.container_id)
        self.journal()
        self.db.provision_roles(self.auth_password, self.rest_password)
        if source:
            self.db.initialize_source()

    def _name(self, component):
        if component not in COMPONENTS:
            raise ValueError('Unsupported component.')
        return f'restoreproof-{self.run_id}-{component}'

    def _inspect(self, identifier):
        return json.loads(self.db._run('inspect', '--format', '{{json .}}', identifier))

    def owned(self, component):
        identifier = self.ids[component]
        return validate_owned(self._inspect(identifier), self.run_id, component, identifier, self.db.container_id)

    def start(self, component, environment):
        name = self._name(component)
        if component in self.attempted or self.db._find('name=^/' + name + '$'):
            raise RuntimeError('Existing application resources are never adopted.')
        self.attempted.add(component)
        self.journal()
        args = ['create', '--name', name, '--label', RUN_LABEL + '=' + self.run_id,
                '--label', COMPONENT_LABEL + '=' + component, '--network', 'container:' + self.db._owned(),
                '--memory', '768m' if component == 'app' else '256m', '--cpus', '1', '--pids-limit', '128',
                '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--tmpfs', '/tmp:rw,nosuid,size=67108864']
        # Environment values go through the subprocess environment, never argv.
        for key in environment:
            args.extend(['--env', key])
        args.append(self.images[component])
        identifier = self.db._run(*args, env=environment).decode().strip()
        if not re.fullmatch(r'[a-f0-9]{64}', identifier):
            raise RuntimeError('Docker did not return an application resource ID.')
        self.ids[component] = identifier
        self.owned(component)
        self.isolation[component] = isolation_evidence(self._inspect(identifier), component, self.db.container_id)
        self.journal()
        self.db._run('start', identifier)

    def start_services(self, *, source=False, missing_config=False):
        from .client import AppClient
        configs = configurations(self.auth_password, self.rest_password, self.jwt_secret, missing_config=missing_config)
        for component in ('mail', 'gateway', 'auth', 'app'):
            self.start(component, configs[component])
        client = AppClient(self)
        client.wait_ready('auth', '/health')
        if source:
            self.db.install_source_app()
        self.start('rest', configs['rest'])
        client.wait_ready('rest', '/')
        client.load_certificate()
        client.wait_ready('app', '/')
        return client

    def stop(self, component):
        self.db._run('stop', '--time', '5', self.owned(component))

    def quiesce(self):
        for component in reversed(COMPONENTS):
            if component in self.ids:
                self.stop(component)

    def snapshot(self):
        return {'database_id': self.db.container_id, 'database_image_id': self.db.image_id,
                'components': dict(self.ids), 'images': dict(self.images),
                'planned_names': {key: self._name(key) for key in sorted(self.attempted)},
                'observed_isolation': dict(self.isolation),
                'network': 'database=none; services=container:<database_id>',
                'published_ports': [], 'host_mounts': []}

    def cleanup(self):
        remaining = list(self.ids.values())
        try:
            found = set(self.db._find('label=' + RUN_LABEL + '=' + self.run_id))
            for component in COMPONENTS:
                found.update(self.db._find('name=^/' + self._name(component) + '$'))
            found.update(cid for cid in self.ids.values() if self.db._find('id=' + cid))
            remaining = sorted(found)
            validated = []
            # Validate the whole set before deleting any resource.
            for identifier in sorted(found):
                item = self._inspect(identifier)
                component = item.get('Config', {}).get('Labels', {}).get(COMPONENT_LABEL)
                if (not self.recovery and component not in self.attempted
                        or component in self.ids and identifier != self.ids[component]):
                    raise RuntimeError('Unrecognized or replaced service resource.')
                validate_owned(item, self.run_id, component, identifier, self.db.container_id)
                validated.append(identifier)
            for identifier in validated:
                self.db._run('rm', '--force', identifier)
            if any(self.db._find('id=' + identifier) for identifier in validated):
                raise RuntimeError('A service remains after cleanup.')
            remaining = self.db._find('label=' + RUN_LABEL + '=' + self.run_id)
            if remaining:
                raise RuntimeError('Unexpected service appeared during cleanup.')
            return self.db.cleanup()
        except (Exception, KeyboardInterrupt):
            return {'status': 'INCOMPLETE', 'remaining': remaining + [self.db.container_id or self.db.name],
                    'message': 'Could not verify the complete owned stack. Use cleanup-app with the recorded run ID.'}


def cleanup_run(run_id):
    stack = ChiselStack(run_id, {'database': 'postgres:17.11-bookworm'})
    stack.recovery = stack.db._recovery_authorized = True
    try:
        candidates = stack.db._find('name=^/' + stack.db.name + '$')
        if len(candidates) == 1:
            stack.db.container_id = candidates[0]
            stack.db._owned()
        elif candidates:
            raise RuntimeError('Ambiguous database identity.')
        return stack.cleanup()
    except (Exception, KeyboardInterrupt):
        return {'status': 'INCOMPLETE', 'remaining': [stack.db.name], 'message': 'Ownership could not be verified.'}
