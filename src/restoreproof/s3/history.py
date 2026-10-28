"""Derive history from authoritative journals; failures never replace success."""
import json
from pathlib import Path
import re

from ..contract import parse_timestamp

MAX_HISTORY_BYTES = 256 * 1024


def summarize(report):
    if (not re.fullmatch(r'[0-9a-f]{32}', report['run_id'])
            or report['status'] not in {'PASS', 'FAIL', 'INCOMPLETE', 'INVALID'}):
        raise ValueError('Invalid history identity/status.')
    parse_timestamp(report['started_at'])
    summary = {key: report.get(key) for key in ('run_id', 'started_at', 'completed_at', 'status',
               'backup', 'implementation', 'failure_code')}
    summary['cleanup_status'] = report.get('cleanup', {}).get('status', 'INCOMPLETE')
    return summary


def merge_history(previous, entry, *, limit=30):
    entries = {item['run_id']: item for item in previous.get('recent_runs', [])}
    entries[entry['run_id']] = entry
    ordered = sorted(entries.values(), key=lambda item: (parse_timestamp(item['started_at']), item['run_id']), reverse=True)
    successful = [item for item in ordered if item['status'] == 'PASS' and item['cleanup_status'] == 'PASS']
    if previous.get('last_success'):
        successful.append(previous['last_success'])
    return {'schema_version': 1, 'latest_attempt': ordered[0],
            'last_success': max(successful, key=lambda item: (parse_timestamp(item['started_at']), item['run_id'])) if successful else None,
            'recent_runs': ordered[:limit]}


def read_history(output, *, limit=30):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('History limit must be 1-100.')
    history = {'schema_version': 1, 'latest_attempt': None, 'last_success': None, 'recent_runs': []}
    count = 0
    for folder in Path(output).glob('*'):
        if not re.fullmatch(r'[0-9a-f]{32}', folder.name) or folder.is_symlink() or not folder.is_dir():
            continue
        count += 1
        if count > 1000:
            raise ValueError('Archive older run directories before reading more than 1000 journals.')
        path = folder / 'report.json'
        if path.is_symlink():
            raise ValueError('History journal must not be a symlink.')
        with path.open('rb') as stream:
            data = stream.read(MAX_HISTORY_BYTES + 1)
        if len(data) > MAX_HISTORY_BYTES:
            raise ValueError('Oversized history journal.')
        report = json.loads(data)
        if report.get('role') != 's3-recovery':
            continue
        if report.get('run_id') != folder.name:
            raise ValueError('History journal identity mismatch.')
        history = merge_history(history, summarize(report), limit=limit)
    return history
