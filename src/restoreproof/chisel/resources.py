"""Exact ownership validation for services sharing a disposable DB namespace."""
import re

RUN_LABEL = 'io.restoreproof.app_run_id'
COMPONENT_LABEL = 'io.restoreproof.app_component'
COMPONENTS = ('mail', 'gateway', 'auth', 'rest', 'app')


def validate_owned(item, run_id, component, identifier, database_id):
    if (not re.fullmatch(r'[a-f0-9]{32}', run_id) or component not in COMPONENTS
            or not re.fullmatch(r'[a-f0-9]{64}', identifier)
            or not re.fullmatch(r'[a-f0-9]{64}', database_id)):
        raise ValueError('Invalid resource identity.')
    labels = item.get('Config', {}).get('Labels', {})
    if (item.get('Id') != identifier
            or item.get('Name', '').lstrip('/') != f'restoreproof-{run_id}-{component}'
            or labels.get(RUN_LABEL) != run_id or labels.get(COMPONENT_LABEL) != component
            or item.get('HostConfig', {}).get('NetworkMode') != 'container:' + database_id):
        raise RuntimeError('Application resource ownership or isolation differs.')
    return identifier


def isolation_evidence(item, component, database_id):
    """Validate observed Docker settings and return only nonsecret metadata."""
    config = item.get('HostConfig', {})
    network = 'none' if component == 'database' else 'container:' + database_id
    tmpfs_path = '/var/lib/postgresql/data' if component == 'database' else '/tmp'
    limits = {'Memory': 768*1024*1024, 'NanoCpus': 1000000000, 'PidsLimit': 128}
    bad_limit = any(type(config.get(key)) is not int or not 0 < config[key] <= maximum
                    for key, maximum in limits.items())
    if (config.get('NetworkMode') != network or config.get('Privileged') or config.get('Binds')
            or config.get('PortBindings') or bad_limit
            or any(mount.get('Type') != 'tmpfs' for mount in item.get('Mounts', []))
            or tmpfs_path not in config.get('Tmpfs', {})):
        raise RuntimeError('Observed container isolation differs from the lab boundary.')
    if component != 'database' and (not config.get('ReadonlyRootfs')
            or 'ALL' not in config.get('CapDrop', [])
            or 'no-new-privileges' not in config.get('SecurityOpt', [])):
        raise RuntimeError('Observed service hardening differs from the lab boundary.')
    return {'network_mode': config['NetworkMode'], 'memory_bytes': config['Memory'],
            'nano_cpus': config['NanoCpus'], 'pids_limit': config['PidsLimit'],
            'read_only_root': config.get('ReadonlyRootfs', False), 'cap_drop': config.get('CapDrop') or [],
            'security_options': config.get('SecurityOpt') or [], 'tmpfs': config['Tmpfs'],
            'host_mounts': [], 'published_ports': []}
