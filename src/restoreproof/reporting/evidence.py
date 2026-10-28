"""Read only explicit inputs; never follow paths or expose arbitrary journal fields."""
from datetime import timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from ..chisel.journey import REQUIRED_CHECKS
from ..contract import _reject_constant, _unique_contract_object, parse_timestamp
from ..engine import EXIT_CODES
from ..s3.contract import S3Backup

MAX_BYTES, MAX_FILES = 256 * 1024, 200
SCOPES = {'aws': 'AWS S3', 'local': 'Local S3 emulator', 'unknown': 'Unclassified storage'}
CHECKS = {'backup-retrieval': 'Exact backup retrieval', 'unauthenticated-denied': 'Unauthenticated access denied',
          'email-otp-login': 'Email OTP sign-in', 'restored-identity': 'Restored identity',
          'saved-brief-content': 'Saved brief content', 'recovered-write-cycle': 'Create, read and update',
          'tenant-isolation': 'Tenant isolation', 'signout': 'Sign-out', 'recovery-duration': 'Recovery duration'}
FAILURES = {'missing-object': 'Object or version missing', 'access-denied': 'S3 access denied',
            'checksum-mismatch': 'Backup checksum mismatch', 'stale-backup': 'Backup capture is too old',
            'download-interrupted': 'Download interrupted', 'download-timeout': 'Download timed out',
            'future-backup': 'Capture timestamp is in the future', 'invalid-contract': 'Invalid recovery contract',
            'recovery-incomplete': 'Application recovery incomplete', 'archive-too-large': 'Archive exceeds size limit',
            'size-mismatch': 'Downloaded size does not match', 'version-mismatch': 'Object version does not match',
            'invalid-content-length': 'Invalid object length', 's3-request-failed': 'S3 request failed',
            'destination-exists': 'Download destination already exists'}


def _scope(endpoint):
    if isinstance(endpoint, str) and re.fullmatch(r'https://s3\.[a-z]{2}-[a-z]+-[1-9]\.amazonaws\.com/?', endpoint):
        return 'aws'
    try:
        parsed = urlsplit(endpoint or '')
        if (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', '::1'} and parsed.port
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                and parsed.path in {'', '/'}):
            return 'local'
    except (ValueError, TypeError):
        pass
    return 'unknown'


def _timestamp(value):
    return parse_timestamp(value).astimezone(timezone.utc).isoformat()


def _number(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e12:
        raise ValueError('Invalid numeric evidence.')
    return value


def _cleanup(report, key):
    record = report.get(key, {})
    status = record.get('status', 'INCOMPLETE')
    if status not in {'PASS', 'INCOMPLETE', 'NOT_REQUIRED'}:
        raise ValueError('Invalid cleanup evidence.')
    if status == 'PASS' and (record.get('remaining') or record.get('archive_retained') is True):
        raise ValueError('Cleanup status contradicts retained resources.')
    return status


def _checks(report):
    raw = report['checks']
    if not isinstance(raw, list) or len(raw) > 40:
        raise ValueError('Invalid check evidence.')
    checks = []
    for item in raw:
        if item['status'] not in EXIT_CODES or not isinstance(item['name'], str) or len(item['name']) > 120:
            raise ValueError('Invalid check evidence.')
        checks.append({'name': item['name'] if item['name'] in CHECKS else 'unrecognized', 'status': item['status'],
                       'http': {key: item[key] for key in ('http', 'create_http', 'read_http', 'update_http',
                                'stale_write_http', 'signout_http', 'afterwards_http')
                                if type(item.get(key)) is int and 100 <= item[key] <= 599}})
    return checks


def _project(report, data):
    if report.get('schema_version') != 1 or report.get('application') != 'chisel':
        raise ValueError('Unsupported recovery evidence.')
    if not re.fullmatch(r'[0-9a-f]{32}', report['run_id']) or report['status'] not in EXIT_CODES:
        raise ValueError('Invalid run identity or status.')
    if type(report['exit_code']) is not int or report['exit_code'] != EXIT_CODES[report['status']]:
        raise ValueError('Run outcome contradicts its exit code.')
    checks = _checks(report)
    cleanup, download = _cleanup(report, 'cleanup'), _cleanup(report, 'download_cleanup')
    backup = S3Backup.model_validate(report['backup']).model_dump(mode='json') if report.get('backup') else None
    if report['status'] == 'PASS':
        required = REQUIRED_CHECKS | {'backup-retrieval', 'recovery-duration'}
        if (not backup or cleanup != 'PASS' or download != 'PASS' or len(checks) != len(required)
                or {item['name'] for item in checks} != required or any(item['status'] != 'PASS' for item in checks)):
            raise ValueError('Successful evidence is incomplete or inconsistent.')
        receipt = report.get('retrieval', {})
        if any(receipt.get(key) != backup[key] for key in ('bucket', 'key', 'version_id', 'sha256', 'expected_bucket_owner')):
            raise ValueError('Retrieved backup contradicts its trusted identity.')
    implementation = report.get('implementation', {})
    digest = implementation.get('source_sha256', '')
    return {'run_id': report['run_id'], 'status': report['status'], 'scope': _scope(report.get('storage_endpoint')),
            'started_at': _timestamp(report['started_at']),
            'completed_at': _timestamp(report['completed_at']) if report.get('completed_at') else None,
            'backup': backup, 'checks': checks, 'cleanup': cleanup, 'download_cleanup': download,
            'failure_code': report.get('failure_code') if report.get('failure_code') in FAILURES else None,
            'seconds': _number(report.get('timings', {}).get('total_seconds')),
            'age_seconds': _number(report.get('retrieval', {}).get('age_seconds')),
            'implementation_sha256': digest if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) else None,
            'input_sha256': hashlib.sha256(data).hexdigest()}


def _paths(inputs):
    paths = []
    for value in inputs:
        path = Path(value)
        if path.is_symlink() or not path.exists():
            raise ValueError('Evidence inputs must exist and cannot be symlinks.')
        candidates = path.rglob('report.json') if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError('Evidence journals must be regular files.')
            paths.append(candidate)
            if len(paths) > MAX_FILES:
                raise ValueError('Select at most 200 report files for one export.')
    return sorted(paths)


def read_evidence(inputs):
    reports, fingerprints = {}, {}
    for path in _paths(inputs):
        try:
            with path.open('rb') as stream:
                data = stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('Oversized evidence file.')
            raw = json.loads(data, parse_constant=_reject_constant, object_pairs_hook=_unique_contract_object)
            if raw.get('role') != 's3-recovery':
                continue
            report = _project(raw, data)
            fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True, allow_nan=False).encode()).hexdigest()
            run_id = report['run_id']
            if run_id in reports and fingerprints[run_id] != fingerprint:
                raise ValueError('Conflicting copies of the same run.')
            reports.setdefault(run_id, report)
            fingerprints[run_id] = fingerprint
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise ValueError('Recovery evidence is invalid, oversized or inconsistent.') from None
    if not reports:
        raise ValueError('No S3 recovery journals found in the selected inputs.')
    return sorted(reports.values(), key=lambda item: (item['started_at'], item['run_id']), reverse=True)
