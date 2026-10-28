"""Static HTML with escaped selected evidence, native disclosures and no network assets."""
from html import escape
from importlib.resources import files

from .evidence import CHECKS, FAILURES, SCOPES


def _text(value):
    return escape(str(value), quote=True)


def _status(value):
    style = 'pass' if value == 'PASS' else 'fail' if value in {'FAIL', 'INVALID'} else 'incomplete'
    return f'<span class="status {style}">{_text(value)}</span>'


def _time(value):
    return _text(value.replace('T', ' ').replace('+00:00', ' UTC')) if value else 'Not recorded'


def _seconds(value):
    return f'{value:,.3f} s' if value is not None else 'Not recorded'


def _outcome(report):
    if report['status'] == 'PASS':
        return 'Application recovery verified'
    return FAILURES.get(report['failure_code'], 'Verification did not establish recovery')


def _state_panel(report, title, kind):
    if report is None:
        return f'<section class="state-panel {kind}"><h3>{title}</h3><p class="empty">No successful recovery in these inputs</p></section>'
    return (f'<section class="state-panel {kind}"><h3>{title}</h3>{_status(report["status"])}'
            f'<p class="outcome">{_outcome(report)}</p><p class="muted">{_time(report["started_at"])}</p>'
            f'<a href="#run-{report["run_id"]}">Inspect run <code>{report["run_id"][:12]}</code></a></section>')


def _facts(pairs):
    return '<dl class="facts">' + ''.join(f'<div><dt>{_text(key)}</dt><dd>{value}</dd></div>' for key, value in pairs) + '</dl>'


def _backup(report):
    backup = report['backup']
    if not backup:
        return '<p class="notice">Backup identity unavailable. This attempt did not retain a valid backup contract.</p>'
    return _facts([
        ('Object', '<code>'+_text(backup['bucket']+'/'+backup['key'])+'</code>'),
        ('Pinned version', '<code>'+_text(backup['version_id'])+'</code>'),
        ('Expected SHA-256', '<code>'+_text(backup['sha256'])+'</code>'),
        ('Source captured', _time(backup['captured_at'])),
        ('Age at verification', _seconds(report['age_seconds'])),
        ('Maximum permitted capture age', _seconds(backup['max_age_seconds'])),
    ])


def _check_table(report):
    if not report['checks']:
        return '<p class="muted">No checks recorded before this journal stopped.</p>'
    rows = []
    for check in report['checks']:
        http = ', '.join(key.replace('_http', '').replace('_', ' ')+' '+str(value) for key, value in check['http'].items())
        rows.append(f'<tr><th scope="row">{CHECKS.get(check["name"], "Unrecognized check")}</th>'
                    f'<td>{_status(check["status"])}</td><td>{_text(http) if http else "—"}</td></tr>')
    return ('<div class="table-scroll" tabindex="0" role="region" aria-label="Recorded checks">'
            '<table><caption>Recorded checks</caption><thead><tr><th scope="col">Check</th><th scope="col">Result</th>'
            '<th scope="col">HTTP evidence</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>')


def _record(report):
    cleanup = lambda key: 'Confirmed' if report[key] == 'PASS' else 'Not confirmed'
    return (f'<details class="record" id="run-{report["run_id"]}"><summary>{_status(report["status"])}'
            f'<span>{_outcome(report)}<small>{_time(report["started_at"])}</small></span>'
            f'<code class="run-short">{report["run_id"][:12]}</code></summary><div class="record-body">'
            f'<p class="run-id">Run <code>{report["run_id"]}</code></p>{_backup(report)}{_check_table(report)}'
            +_facts([('Target cleanup', cleanup('cleanup')), ('Download cleanup', cleanup('download_cleanup')),
                     ('Whole attempt, including cleanup', _seconds(report['seconds'])),
                     ('Completed', _time(report['completed_at']))])+
            f'<p class="fingerprint">Input JSON SHA-256 <code>{report["input_sha256"]}</code></p>'
            f'<p class="fingerprint">Implementation SHA-256 <code>{report["implementation_sha256"] or "Not recorded"}</code></p>'
            '</div></details>')


def _scope_section(scope, reports, success):
    explanations = {
        'aws': 'AWS regional S3 endpoint recorded. The Chisel adapter uses disposable Docker containers; this does not prove GitHub OIDC or production disaster recovery.',
        'local': 'Loopback S3 endpoint recorded. This synthetic lab exercises real Chisel containers; it does not validate AWS IAM, federation or cloud durability.',
        'unknown': 'The recorded storage endpoint is missing or outside the recognized AWS/loopback forms. No cloud provenance is inferred.',
    }
    return (f'<section class="scope" id="scope-{scope}" aria-labelledby="title-{scope}">'
            f'<div class="scope-heading"><div><h2 id="title-{scope}">{SCOPES[scope]}</h2>'
            f'<p>{explanations[scope]}</p></div><span class="count">{len(reports)} recorded attempts</span></div>'
            '<div class="states">'+_state_panel(reports[0], 'Latest attempt', 'latest')+
            _state_panel(success, 'Last successful recovery', 'success')+'</div>'
            '<div class="records"><h3>Attempt history</h3><p class="muted">Newest first. Expand a run to inspect its backup and checks.</p>'
            +''.join(_record(report) for report in reports)+'</div></section>')


def render(reports, groups, generated_at):
    css = files('restoreproof.reporting').joinpath('report.css').read_text(encoding='utf-8')
    sections = []
    for group in groups:
        members = [report for report in reports if report['scope'] == group['scope']]
        success = next((r for r in members if r['status'] == 'PASS'), None)
        sections.append(_scope_section(group['scope'], members, success))
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<meta name="color-scheme" content="light"><title>RestoreProof · Recovery evidence</title>'
            f'<style>{css}</style></head><body><a class="skip-link" href="#evidence">Skip to evidence</a>'
            '<header class="masthead"><a class="brand" href="#top"><span class="brand-mark" aria-hidden="true">R</span>RestoreProof</a>'
            '<nav aria-label="Report navigation"><a href="#evidence">Evidence</a><a href="#reading">Reading this report</a></nav></header>'
            '<main id="top"><div class="intro"><div><h1>Recovery evidence</h1>'
            '<p>A failed attempt stays visible.<br>The last proven recovery stays identifiable.</p></div>'
            f'<div class="edition"><strong>Offline report</strong><span>{len(reports)} attempts across {len(groups)} storage scopes</span>'
            f'<span>Exported {_time(generated_at)}</span></div></div>'
            '<p class="snapshot-note">Historical evidence snapshot. Exporting this page does not run a new recovery or confirm that a backup is still fresh.</p>'
            '<div id="evidence">'+''.join(sections)+'</div>'
            '<section class="reading" id="reading"><h2>Reading this report</h2>'
            '<p><strong>PASS</strong> requires all recorded application checks and both cleanup results. '
            '<strong>FAIL</strong> disproves an expectation. <strong>INCOMPLETE</strong> means recovery was not established. '
            '<strong>INVALID</strong> means the supplied recovery input was rejected.</p>'
            '<p>Controlled failure demonstrations intentionally produce unsuccessful attempts. They remain unsuccessful here. '
            'Each storage scope has its own latest attempt and last success, derived only from the selected inputs; this is not a global service-health view.</p>'
            '<p>Timings describe the recorded synthetic workload and are not production RTO/RPO. The scope label comes from the recorded endpoint, '
            'not independent proof of cloud identity. Input fingerprints identify supplied bytes; they are not signatures or authenticity guarantees.</p>'
            '<p>Only selected evidence fields are included. Credentials, raw error text and local paths are omitted. '
            'Object names and identifiers remain visible. Keep exports private when their source evidence is private.</p>'
            '<p class="muted">This file has no external assets or executable scripts. Use your browser’s Print command to save a PDF; expanded run records are included.</p>'
            '</section></main><footer>RestoreProof · Application recovery verification</footer></body></html>')
