"""Atomic JSON evidence and CI-readable JUnit outcomes."""

import json
import os
from pathlib import Path
import re
import tempfile
from xml.etree import ElementTree as ET


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix='.restoreproof-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _xml_text(value: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '\ufffd', value)


def _junit(report: dict) -> str:
    outcomes = list(report.get('checks', []))
    cleanup = report.get('cleanup', {'status': 'NOT_REQUIRED'})
    if cleanup.get('status') != 'NOT_REQUIRED':
        outcomes.append({'name': 'cleanup', **cleanup})
    if report['status'] in {'INVALID', 'INCOMPLETE'}:
        outcomes.append({'name': 'verification-run', 'status': 'INCOMPLETE',
                         'reason': report.get('errors', [])})
    failures = sum(c['status'] == 'FAIL' for c in outcomes)
    errors = sum(c['status'] not in {'PASS', 'FAIL'} for c in outcomes)
    suite = ET.Element('testsuite', name='RestoreProof', tests=str(len(outcomes)),
                       failures=str(failures), errors=str(errors))
    for outcome in outcomes:
        case = ET.SubElement(suite, 'testcase', name=_xml_text(outcome['name']))
        status = outcome['status']
        if status == 'PASS':
            continue
        element = ET.SubElement(case, 'failure' if status == 'FAIL' else 'error', type=status)
        element.text = _xml_text(json.dumps(outcome, ensure_ascii=True, allow_nan=False))
    ET.indent(suite)
    return ET.tostring(suite, encoding='unicode', xml_declaration=True) + '\n'


def write_report(folder: Path, report: dict) -> None:
    """Each file is atomically replaced; JSON is the authoritative journal."""
    folder.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + '\n'
    junit = _junit(report)
    # Publish the authoritative success journal only after its companion succeeds.
    _atomic_write(folder / 'junit.xml', junit)
    _atomic_write(folder / 'report.json', payload)
