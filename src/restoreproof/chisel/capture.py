"""Capture expectations before faults; quiesce the real source before pg_dump."""
import hashlib
import json
from pathlib import Path
import uuid

from .contract import AppContract, SOURCE_COMMIT
from .fixtures import seed
from .stack import ChiselStack
from ..engine import _new_report, _phase
from ..reports import write_report


def capture(output, images, scenario):
    run_id = uuid.uuid4().hex
    folder = Path(output).resolve() / ('source-' + run_id)
    folder.mkdir(parents=True, exist_ok=False)
    report = _new_report(run_id, folder)
    report.update(application='chisel', role='source-capture', scenario=scenario)
    stack = None

    def journal():
        if stack:
            report['target'] = stack.snapshot()
        write_report(folder, report)

    journal()
    contract_path = folder / 'contract.json'
    try:
        stack = ChiselStack(run_id, images, journal=journal)
        report['cleanup'] = {'status': 'INCOMPLETE', 'remaining': [stack.db.name]}
        _phase(report, folder, 'create-source', lambda: stack.create_database(source=True))
        client = _phase(report, folder, 'start-source', lambda: stack.start_services(source=True))
        expectation = _phase(report, folder, 'seed-through-http', lambda: seed(client))
        # Independent baseline survives subsequent deletion/schema corruption.
        (folder / 'expectation.json').write_text(json.dumps(expectation, indent=2) + '\n', encoding='utf-8')
        _phase(report, folder, 'quiesce-source', stack.quiesce)
        if scenario == 'missing-data':
            stack.db.execute(f"DELETE FROM public.chisel_briefs WHERE id = '{expectation['brief_id']}';")
        if scenario == 'incompatible-schema':
            stack.db.execute('DROP FUNCTION public.chisel_save_brief(uuid,uuid,integer,jsonb);')
        archive = folder / 'source.dump'
        _phase(report, folder, 'capture-backup', lambda: stack.db.dump(archive))
        payload = {'version': 1, 'application': 'chisel', 'source_commit': SOURCE_COMMIT,
                   'backup': {'path': archive.name, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}, **expectation}
        AppContract.model_validate(payload)
        contract_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        report['status'], report['exit_code'] = 'PASS', 0
    except (Exception, KeyboardInterrupt) as error:
        report['errors'].append(f'{report["phase"]} did not complete ({type(error).__name__}).')
        raise
    finally:
        if stack:
            report['target'] = stack.snapshot()
            report['cleanup'] = stack.cleanup()
            if report['cleanup']['status'] != 'PASS':
                report['status'], report['exit_code'] = 'INCOMPLETE', 2
        report['phase'] = 'complete'
        journal()
    if report['status'] != 'PASS':
        raise RuntimeError('Source capture cleanup was not verified.')
    return contract_path, report
