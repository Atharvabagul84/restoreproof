"""Retrieve a trusted exact backup, run Chisel recovery, and journal cleanup."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

from .contract import load_contract
from .provenance import implementation
from .retrieval import retrieve, RetrievalError
from ..chisel.journey import REQUIRED_CHECKS
from ..chisel.runner import verify_app
from ..contract import ContractError
from ..engine import EXIT_CODES, _new_report, _phase
from ..reports import _atomic_write, write_report


def _record_application(report, child):
    report['application_recovery'] = {key: child[key] for key in ('run_id', 'report_path', 'status', 'cleanup')}
    report['target'] = child.get('target', {})
    report['cleanup'] = child['cleanup']
    report['checks'].extend(child['checks'])
    names = [check['name'] for check in child['checks']]
    if child['status'] == 'PASS' and (set(names) != REQUIRED_CHECKS | {'recovery-duration'}
            or len(names) != len(set(names)) or any(check['status'] != 'PASS' for check in child['checks'])
            or child['exit_code'] != 0):
        raise RuntimeError('Application evidence is incomplete.')
    report['status'] = child['status']


def run_drill(contract_path, output, *, client, images=None):
    run_id = uuid.uuid4().hex
    folder = Path(output).resolve() / run_id
    folder.mkdir(parents=True, exist_ok=False)
    report = _new_report(run_id, folder)
    report.update(role='s3-recovery', application='chisel', implementation=implementation(),
                  storage_endpoint=client.meta.endpoint_url)
    report['measurement_boundary'] = 'End-to-end attempt includes retrieval and application recovery; total includes cleanup and any image preparation. Not production RTO.'
    archive = folder / 'backup.dump'
    started = time.monotonic()
    write_report(folder, report)
    try:
        contract = load_contract(contract_path)
        report['backup'] = contract.backup.model_dump(mode='json')
        receipt = _phase(report, folder, 'retrieve-backup', lambda: retrieve(client, contract.backup, archive))
        report['retrieval'] = receipt
        report['checks'].append({'name': 'backup-retrieval', 'status': 'PASS', 'sha256': receipt['sha256'],
                                 'version_id': receipt['version_id'], 'age_seconds': receipt['age_seconds']})
        report['download_cleanup'] = {'status': 'INCOMPLETE'}
        payload = contract.model_dump(mode='json')
        payload['backup'] = {'path': archive.name, 'sha256': receipt['sha256']}
        local_contract = folder / 'application-contract.json'
        _atomic_write(local_contract, json.dumps(payload, indent=2) + '\n')
        # A child exception can lose its cleanup result; uncertainty must not become PASS.
        report['cleanup'] = {'status': 'INCOMPLETE', 'remaining': [], 'application_allocated': 'unknown'}
        child = _phase(report, folder, 'application-recovery', lambda: verify_app(local_contract, folder / 'application', images=images))
        _record_application(report, child)
    except ContractError:
        report['status'], report['failure_code'] = 'INVALID', 'invalid-contract'
        report['errors'].append('Invalid S3 recovery contract.')
    except RetrievalError as error:
        report['status'], report['failure_code'] = error.status, error.code
        report['checks'].append({'name': 'backup-retrieval', 'status': error.status, 'reason': error.code})
        report['errors'].append(error.code)
    except (Exception, KeyboardInterrupt) as error:
        report['status'] = 'INCOMPLETE'
        report['failure_code'] = 'recovery-incomplete'
        report['errors'].append(f'{report["phase"]} incomplete ({type(error).__name__}).')
    finally:
        try:
            archive.unlink(missing_ok=True)
            if any(folder.glob('.s3-download-*')):
                raise OSError('Partial download remains.')
            report['download_cleanup'] = {'status': 'PASS', 'archive_retained': False}
        except OSError:
            report['download_cleanup'] = {'status': 'INCOMPLETE'}
        if report['cleanup']['status'] == 'NOT_REQUIRED':
            report['cleanup'] = {'status': 'PASS', 'remaining': [], 'application_allocated': False}
        if report['cleanup']['status'] != 'PASS' or report['download_cleanup']['status'] != 'PASS':
            report['status'] = 'INCOMPLETE'
            report['cleanup']['status'] = 'INCOMPLETE'
        report['timings']['total_seconds'] = round(time.monotonic() - started, 6)
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        report['phase'], report['exit_code'] = 'complete', EXIT_CODES[report['status']]
        write_report(folder, report)
    return report
