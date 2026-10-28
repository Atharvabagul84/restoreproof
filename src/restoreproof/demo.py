"""Synthetic, quiesced fixtures; no application or production credentials."""

import hashlib
from importlib.resources import files
import json
from pathlib import Path
import uuid

from .contract import APPROVED_IMAGE
from .docker_postgres import DockerPostgres

SNAPSHOT_SQL = """SELECT json_build_object(
    'teams', (SELECT json_agg(row_to_json(t)) FROM (SELECT * FROM app.teams ORDER BY id) t),
    'features', (SELECT json_agg(row_to_json(t)) FROM (SELECT * FROM app.features ORDER BY id) t),
    'snapshots', (SELECT json_agg(row_to_json(t)) FROM (SELECT * FROM app.snapshots ORDER BY feature_id, revision) t),
    'checkpoints', (SELECT json_agg(row_to_json(t)) FROM (SELECT * FROM app.checkpoints ORDER BY id) t)
)"""
INVARIANT_SQL = """SELECT to_json(NOT EXISTS (
    SELECT 1 FROM app.features f LEFT JOIN app.snapshots s
    ON s.feature_id = f.id AND s.revision = f.revision
    WHERE s.feature_id IS NULL
))"""
FRESHNESS_SQL = """SELECT to_json(to_char(max(committed_at) AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS"Z"')) FROM app.checkpoints"""


class DemoError(RuntimeError):
    pass


def _json_file(path, payload):
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def create_demo(output: Path, scenario: str, image: str = APPROVED_IMAGE) -> Path:
    if scenario not in {'healthy', 'stale', 'inconsistent', 'corrupt', 'ledger-healthy', 'ledger-gap', 'application', 'application-broken'}:
        raise ValueError('Unknown demo scenario.')
    source_id = uuid.uuid4().hex
    folder = Path(output).resolve() / ('fixture-' + source_id)
    folder.mkdir(parents=True, exist_ok=False)
    journal = {'source_run_id': source_id, 'scenario': scenario, 'status': 'INCOMPLETE',
               'phase': 'create', 'clock': 'synthetic fixed logical time, not observed production data loss'}
    journal_path = folder / 'source.json'
    _json_file(journal_path, journal)
    source = DockerPostgres(image, source_id, timeout_seconds=120)
    try:
        journal['target'] = source.create()
        journal['phase'] = 'seed'
        _json_file(journal_path, journal)
        source.execute(files('restoreproof').joinpath('fixtures/seed.sql').read_text(encoding='utf-8'))
        ledger = None
        if scenario.startswith('ledger-'):
            from .ledger_demo import prepare_ledger
            ledger = prepare_ledger(source, folder, scenario)
        if scenario.startswith('application'):
            from .application_journey import prepare_orders
            prepare_orders(source)
            if scenario == 'application-broken':
                source.execute('DELETE FROM orders_app.orders;')
        if scenario == 'inconsistent':
            source.execute('DELETE FROM app.snapshots WHERE feature_id=101 AND revision=2;')
        # No writers run between manifest capture and pg_dump: same quiesced fixture.
        manifest = source.query(SNAPSHOT_SQL)
        _json_file(folder / 'snapshot-manifest.json', manifest)
        archive = folder / 'backup.dump'
        journal['phase'] = 'dump'
        _json_file(journal_path, journal)
        source.dump(archive)
        if scenario == 'corrupt':
            archive.write_bytes(archive.read_bytes()[:12])  # Keep PGDMP; test pg_restore, not only SHA.
        incident = '2026-01-01T00:02:00Z' if scenario == 'stale' else '2026-01-01T00:00:30Z'
        contract = {
            'version': 1, 'image': image,
            'backup': {'path': 'backup.dump', 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()},
            'checks': [
                {'name': 'snapshot-data', 'sql': SNAPSHOT_SQL, 'expected': manifest},
                {'name': 'revision-snapshots', 'sql': INVARIANT_SQL, 'expected': True},
            ],
            'freshness': {'sql': FRESHNESS_SQL, 'incident_at': incident, 'max_data_age_seconds': 60},
            'max_restore_seconds': 300,
        }
        if ledger is not None:
            contract['ledger'] = ledger
        if scenario.startswith('application'):
            contract['application_journey'] = True
        _json_file(folder / 'contract.json', contract)
        journal['status'] = 'PASS'
    except (Exception, KeyboardInterrupt) as error:
        journal['error'] = f'Fixture operation failed ({type(error).__name__}).'
    finally:
        journal['cleanup'] = source.cleanup()
        if journal['cleanup']['status'] != 'PASS':
            journal['status'] = 'INCOMPLETE'
        journal['phase'] = 'finished'
        _json_file(journal_path, journal)
    if journal['status'] != 'PASS':
        raise DemoError(f'Fixture preparation incomplete. Inspect {journal_path}')
    return folder / 'contract.json'
