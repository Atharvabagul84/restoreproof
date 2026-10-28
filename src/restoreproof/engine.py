"""Restore lifecycle orchestration; external operations stay in the adapter."""

from datetime import datetime, timezone
from pathlib import Path
import time
import uuid

from .contract import ContractError, load_contract, verify_archive
from .evaluation import evaluate_check, evaluate_freshness
from .reports import write_report

EXIT_CODES = {'PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2, 'INVALID': 3}


def _new_report(run_id: str, folder: Path) -> dict:
    return {
        'schema_version': 1, 'run_id': run_id,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'status': 'INCOMPLETE', 'exit_code': 2, 'phase': 'preflight',
        'report_path': str(folder / 'report.json'), 'checks': [], 'errors': [],
        'cleanup': {'status': 'NOT_REQUIRED', 'remaining': []}, 'target': {},
        'timings': {},
        'measurement_boundary': 'Before contract preflight through application/checkpoint verification; cleanup recorded separately.',
    }


def _phase(report, folder, name, action):
    report['phase'] = name
    write_report(folder, report)
    start = time.monotonic()
    try:
        return action()
    finally:
        report['timings'][name + '_seconds'] = round(time.monotonic() - start, 6)


def _checks(contract, target, report):
    for spec in contract.checks:
        report['checks'].append(evaluate_check(spec, target.query(spec.sql)))
    report['checks'].append(evaluate_freshness(contract.freshness, target.query(contract.freshness.sql)))


def _verification_status(checks):
    if any(c['status'] == 'INCOMPLETE' for c in checks):
        return 'INCOMPLETE'
    return 'FAIL' if any(c['status'] == 'FAIL' for c in checks) else 'PASS'


def _load_ledger(contract, contract_path):
    if contract.ledger is None:
        return None
    from .ledger import LedgerError, load_ledger
    try:
        path = Path(contract_path).resolve().parent / contract.ledger.path
        return load_ledger(path, contract.ledger.sha256)
    except LedgerError as error:
        raise ContractError(str(error)) from None


def _ledger_checks(contract, ledger, target, report):
    from .ledger import compare_ledger
    report['checks'].append(compare_ledger(ledger, target.query(contract.ledger.sql),
                                           incident_at=contract.freshness.incident_at))


def _application_checks(target, report, runner):
    if runner is None:
        from .application_journey import run_application_journey
        runner = run_application_journey
    checks = runner(target)
    if (not isinstance(checks, list) or not checks or any(
            not isinstance(c, dict) or not isinstance(c.get('name'), str)
            or not c['name'].startswith('application-')
            or c.get('status') not in {'PASS', 'FAIL', 'INCOMPLETE'} for c in checks)):
        raise RuntimeError('Application journey did not provide valid evidence.')
    if len({c['name'] for c in checks}) != len(checks):
        raise RuntimeError('Application journey returned duplicate check names.')
    if all(c['status'] == 'PASS' for c in checks):
        from .application_journey import REQUIRED_APPLICATION_CHECKS
        if {c['name'] for c in checks} != REQUIRED_APPLICATION_CHECKS:
            raise RuntimeError('Application journey did not complete every required check.')
    report['checks'].extend(checks)


def _cleanup(target, report, folder):
    start = time.monotonic()
    report['phase'] = 'cleanup'
    # Cleanup must still run if a disk/report write fails after allocation.
    try:
        report['cleanup'] = target.cleanup()
    except (Exception, KeyboardInterrupt) as error:
        report['cleanup'] = {'status': 'INCOMPLETE', 'remaining': [report['run_id']],
                             'message': f'Cleanup did not complete ({type(error).__name__}).'}
    report['timings']['cleanup_seconds'] = round(time.monotonic() - start, 6)
    if report['cleanup']['status'] != 'PASS':
        report['status'] = 'INCOMPLETE'


def verify(contract_path: Path, output: Path, *, backend_factory=None, application_runner=None) -> dict:
    """Create a fresh target, verify it, clean it, and retain distinct run evidence."""
    run_id = uuid.uuid4().hex
    folder = Path(output).resolve() / run_id
    folder.mkdir(parents=True, exist_ok=False)
    report = _new_report(run_id, folder)
    target = None
    started = time.monotonic()
    write_report(folder, report)
    try:
        contract = load_contract(Path(contract_path))
        archive = verify_archive(contract, Path(contract_path))
        ledger = _load_ledger(contract, contract_path)
        if contract.ledger is not None:
            report['ledger_sha256'] = contract.ledger.sha256.lower()
        report['archive_sha256'] = contract.backup.sha256
        report['image_reference'] = contract.image
        if backend_factory is None:
            from .docker_postgres import DockerPostgres
            backend_factory = DockerPostgres
        target = backend_factory(image=contract.image, run_id=run_id,
                                 timeout_seconds=min(contract.max_restore_seconds, 120))
        report['target'] = _phase(report, folder, 'create', target.create)
        _phase(report, folder, 'restore', lambda: target.restore(archive, contract.backup.sha256))
        _phase(report, folder, 'checks', lambda: _checks(contract, target, report))
        if ledger is not None:
            _phase(report, folder, 'ledger', lambda: _ledger_checks(contract, ledger, target, report))
        if contract.application_journey:
            _phase(report, folder, 'application', lambda: _application_checks(target, report, application_runner))
        elapsed = time.monotonic() - started
        report['timings']['verification_attempt_seconds'] = round(elapsed, 6)
        report['checks'].append({
            'name': 'recovery-duration', 'status': 'PASS' if elapsed <= contract.max_restore_seconds else 'FAIL',
            'actual_seconds': round(elapsed, 6), 'max_seconds': contract.max_restore_seconds,
        })
        report['status'] = _verification_status(report['checks'])
    except ContractError as error:
        report['status'] = 'INVALID'
        report['errors'].append({'phase': report['phase'], 'message': str(error)})
    except KeyboardInterrupt:
        report['errors'].append({'phase': report['phase'], 'message': 'Interrupted; verification is incomplete.'})
        report['status'] = 'INCOMPLETE'
    except Exception as error:
        # Adapter/provider output can contain data or secrets; preserve the phase and type only.
        report['errors'].append({'phase': report['phase'], 'message': f'Operation failed ({type(error).__name__}).'})
        report['status'] = 'INCOMPLETE'
    finally:
        if target is not None:
            _cleanup(target, report, folder)
        report['phase'] = 'finished'
        report['exit_code'] = EXIT_CODES[report['status']]
        report['timings']['total_seconds'] = round(time.monotonic() - started, 6)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_report(folder, report)
    return report
