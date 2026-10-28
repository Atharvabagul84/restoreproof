"""Application recovery verification with incremental, sanitized evidence."""
from pathlib import Path
import time
import uuid

from .contract import load_contract, SOURCE_COMMIT
from .images import prepare_images
from .journey import REQUIRED_CHECKS, run_journey
from .stack import ChiselStack
from ..contract import ContractError, verify_archive
from ..engine import EXIT_CODES, _new_report, _phase, _verification_status
from ..reports import write_report


def verify_app(contract_path, output, *, images=None, fault=None):
    if fault not in {None, 'auth-unavailable', 'missing-config'}:
        raise ValueError('Unknown fixed recovery fault.')
    run_id = uuid.uuid4().hex
    folder = Path(output).resolve() / run_id
    folder.mkdir(parents=True, exist_ok=False)
    report = _new_report(run_id, folder)
    report.update(application='chisel', source_commit=SOURCE_COMMIT, fault=fault)
    report['measurement_boundary'] = 'Preflight through fresh database restore, service startup and app checks. Image preparation and source capture excluded; cleanup separate.'
    stack = None

    def journal():
        if stack:
            report['target'] = stack.snapshot()
        write_report(folder, report)

    def record(check):
        if (not isinstance(check, dict) or check.get('name') not in REQUIRED_CHECKS | {'recovery-duration'}
                or check.get('status') not in {'PASS', 'FAIL', 'INCOMPLETE'}
                or any(item['name'] == check['name'] for item in report['checks'])):
            raise RuntimeError('Invalid or duplicate application evidence.')
        report['checks'].append(check)
        journal()

    journal()
    started = time.monotonic()
    try:
        contract = load_contract(Path(contract_path))
        archive = verify_archive(contract, Path(contract_path))
        report['backup_sha256'] = contract.backup.sha256
        # Downloads/builds are outside the measured recovery window.
        if images is None:
            preparation_started = time.monotonic()
            images = _phase(report, folder, 'prepare-images', prepare_images)
            started += time.monotonic() - preparation_started
        stack = ChiselStack(run_id, images, journal=journal)
        report['cleanup'] = {'status': 'INCOMPLETE', 'remaining': [stack.db.name]}
        _phase(report, folder, 'create-database', stack.create_database)
        _phase(report, folder, 'restore', lambda: stack.db.restore(archive, contract.backup.sha256))
        client = _phase(report, folder, 'start-services', lambda: stack.start_services(missing_config=fault == 'missing-config'))
        if fault == 'auth-unavailable':
            stack.stop('auth')
            state = stack._inspect(stack.owned('auth'))['State']['Status']
            if state != 'exited':
                raise RuntimeError('Auth fault injection did not stop the owned service.')
            report['fault_injection'] = {'component': 'auth', 'container_id': stack.ids['auth'], 'observed_state': state}
        _phase(report, folder, 'application-journey', lambda: run_journey(client, contract, record))
        if {item['name'] for item in report['checks']} != REQUIRED_CHECKS:
            raise RuntimeError('Application acceptance check set is incomplete.')
        elapsed = time.monotonic() - started
        record({'name': 'recovery-duration', 'status': 'PASS' if elapsed <= contract.max_recovery_seconds else 'FAIL',
                'observed_seconds': round(elapsed, 6), 'maximum_seconds': contract.max_recovery_seconds})
        report['status'] = _verification_status(report['checks'])
    except ContractError as error:
        report['status'] = 'INVALID'
        report['errors'].append(str(error))
    except (Exception, KeyboardInterrupt) as error:
        report['status'] = 'INCOMPLETE'
        report['failure_phase'] = report['phase']
        report['error_type'] = type(error).__name__
        # No upstream responses, credentials, cookies, code or OTP in persisted logs.
        report['errors'].append(f'{report["phase"]} did not complete ({type(error).__name__}).')
    finally:
        report['timings']['verification_seconds'] = round(time.monotonic() - started, 6)
        if stack:
            report['phase'] = 'cleanup'
            report['target'] = stack.snapshot()
            cleanup_started = time.monotonic()
            report['cleanup'] = stack.cleanup()
            report['timings']['cleanup_seconds'] = round(time.monotonic() - cleanup_started, 6)
            if report['cleanup']['status'] != 'PASS':
                report['status'] = 'INCOMPLETE'
        report['phase'] = 'complete'
        report['exit_code'] = EXIT_CODES[report['status']]
        journal()
    return report
