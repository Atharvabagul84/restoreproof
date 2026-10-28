"""Real Chisel recovery from an older object version plus five storage faults."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid

from .contract import S3RecoveryContract
from .drill import run_drill
from .evidence import publish_report
from .fault_server import interrupted_download
from .lab import local_storage
from ..chisel.capture import capture
from ..chisel.images import prepare_images
from ..reports import _atomic_write

SCENARIOS = {'healthy': 'PASS', 'missing-object': 'INCOMPLETE', 'access-denied': 'INCOMPLETE',
             'checksum-mismatch': 'FAIL', 'stale-backup': 'FAIL', 'download-interrupted': 'INCOMPLETE'}


def _scenario(scenario, base, folder, client, images, size):
    payload = deepcopy(base)
    backup = payload['backup']
    if scenario == 'missing-object':
        backup['version_id'] = 'missing-version'
    elif scenario == 'checksum-mismatch':
        backup['sha256'] = '0' * 64
    elif scenario == 'stale-backup':
        backup['captured_at'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    path = folder / (scenario + '.json')
    _atomic_write(path, json.dumps(payload, indent=2) + '\n')
    if scenario == 'download-interrupted':
        with interrupted_download(backup['version_id'], size) as broken:
            return run_drill(path, folder / 'drills', client=broken, images=images)
    if scenario == 'access-denied':
        policy = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Principal': '*',
            'Action': 's3:GetObject*', 'Resource': f'arn:aws:s3:::{backup["bucket"]}/{backup["key"]}'}]}
        client.put_bucket_policy(Bucket=backup['bucket'], Policy=json.dumps(policy))
    try:
        return run_drill(path, folder / 'drills', client=client, images=images)
    finally:
        if scenario == 'access-denied':
            client.delete_bucket_policy(Bucket=backup['bucket'])


def run_demo(output):
    folder = Path(output).resolve() / ('suite-' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    suite = {'status': 'INCOMPLETE', 'scenarios': [], 'summary_path': str(folder/'suite.json'),
             'storage': 'local Moto over HTTP; not live AWS', 'storage_cleanup': 'INCOMPLETE'}

    def save():
        _atomic_write(folder/'suite.json', json.dumps(suite, indent=2) + '\n')

    save()
    lab = None
    try:
        images = prepare_images()
        app_contract, source = capture(folder / 'source', images, 'healthy')
        suite.update(source_cleanup=source['cleanup'], source_report_path=source['report_path'],
                     source_contract_path=str(app_contract))
        payload = json.loads(app_contract.read_text())
        archive = app_contract.parent / payload['backup']['path']
        data = archive.read_bytes()
        with local_storage() as lab:
            client, bucket = lab['client'], lab['bucket']
            key = 'backups/chisel/source.dump'
            version = client.put_object(Bucket=bucket, Key=key, Body=data)['VersionId']
            newer = client.put_object(Bucket=bucket, Key=key, Body=b'PGDMPnewer-unwanted-version')['VersionId']
            suite.update(original_version_id=version, newer_version_id=newer)
            payload['backup'] = dict(bucket=bucket, key=key, version_id=version,
                sha256=payload['backup']['sha256'], expected_bucket_owner='123456789012',
                captured_at=source['started_at'], max_age_seconds=86400)
            S3RecoveryContract.model_validate(payload)
            for scenario, expected in SCENARIOS.items():
                report = _scenario(scenario, payload, folder, client, images, len(data))
                matched = (report['status'] == expected and report['cleanup']['status'] == 'PASS'
                           and report['download_cleanup']['status'] == 'PASS')
                if scenario != 'healthy':
                    matched = matched and report.get('failure_code') == scenario and report['target'] == {}
                suite['scenarios'].append(dict(scenario=scenario, status=report['status'],
                    expected=expected, matched_expected_cause=matched, report_path=report['report_path']))
                suite['history'] = publish_report(client, report['report_path'], bucket=bucket,
                                                  expected_bucket_owner='123456789012')
                save()
        suite['storage_cleanup'] = lab['cleanup']
        if (len(suite['scenarios']) == len(SCENARIOS) and suite['storage_cleanup'] == 'PASS'
                and suite['source_cleanup']['status'] == 'PASS'
                and all(item['matched_expected_cause'] for item in suite['scenarios'])):
            suite['status'] = 'PASS'
    finally:
        if lab is not None:
            suite['storage_cleanup'] = lab['cleanup']
        save()
    return suite
