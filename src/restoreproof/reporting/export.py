"""Create an offline report only after all selected evidence has been validated."""
from datetime import datetime, timezone
from pathlib import Path

from .evidence import read_evidence, SCOPES
from .render import render
from ..reports import _atomic_write


def write_html(inputs, output):
    output = Path(output)
    if output.suffix.lower() != '.html' or output.is_symlink():
        raise ValueError('Choose a regular .html output, separate from JSON evidence.')
    reports = read_evidence(inputs)
    groups = []
    for scope, label in SCOPES.items():
        members = [report for report in reports if report['scope'] == scope]
        if not members:
            continue
        short = lambda item: {key: item[key] for key in ('run_id', 'status', 'started_at')}
        success = next((r for r in members if r['status'] == 'PASS'), None)
        groups.append({'scope': scope, 'label': label, 'run_count': len(members),
                       'latest_attempt': short(members[0]), 'last_success': short(success) if success else None})
    generated_at = datetime.now(timezone.utc).isoformat()
    document = render(reports, groups, generated_at)
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output, document)
    return {'export_status': 'PASS', 'run_count': len(reports), 'scopes': groups,
            'generated_at': generated_at, 'output_path': str(output.resolve())}
