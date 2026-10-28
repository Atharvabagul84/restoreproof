"""One-command real-app recovery and explicit expected negative outcomes."""
import json
from pathlib import Path
import uuid
from .capture import capture
from .images import prepare_images
from .runner import verify_app

SCENARIOS = {'healthy': 'PASS', 'missing-data': 'FAIL', 'incompatible-schema': 'FAIL',
             'auth-unavailable': 'INCOMPLETE', 'missing-config': 'INCOMPLETE'}


def matches_scenario(scenario, report):
    """An unrelated incomplete run is never evidence of an intended fault."""
    if (report['status'] != SCENARIOS[scenario]
            or report['cleanup']['status'] != 'PASS' or report['source_cleanup']['status'] != 'PASS'):
        return False
    checks = {check['name']: check for check in report['checks']}
    if scenario == 'healthy':
        return True  # The verifier enforces the complete, unique acceptance set.
    if scenario in {'missing-data', 'incompatible-schema'}:
        failed = {name for name, check in checks.items() if check['status'] == 'FAIL'}
        expected = 'saved-brief-content' if scenario == 'missing-data' else 'recovered-write-cycle'
        return failed == {expected} and checks.get('restored-identity', {}).get('status') == 'PASS'
    authentication = checks.get('email-otp-login', {})
    if (report.get('failure_phase') != 'application-journey'
            or report.get('error_type') != 'DependencyUnavailable'
            or authentication.get('status') != 'INCOMPLETE'):
        return False
    if scenario == 'missing-config':
        return authentication.get('http') == 503
    return (report.get('fault_injection', {}).get('observed_state') == 'exited'
            and authentication.get('http') in {502, None})


def run_demo(output, scenario='healthy', *, images=None):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario.')
    images = images or prepare_images()
    contract, source = capture(output, images, scenario)
    result = verify_app(contract, output, images=images,
                        fault=scenario if scenario in {'auth-unavailable', 'missing-config'} else None)
    result['source_report_path'] = source['report_path']
    result['source_cleanup'] = source['cleanup']
    result['source_run_id'] = source['run_id']
    result['contract_path'] = str(contract)
    result['scenario'] = scenario
    from ..reports import write_report
    write_report(Path(result['report_path']).parent, result)
    return result


def run_suite(output):
    folder = Path(output).resolve() / ('suite-' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    suite = {'status': 'INCOMPLETE', 'scenarios': [], 'summary_path': str(folder / 'suite.json')}
    def save():
        from ..reports import _atomic_write
        _atomic_write(folder / 'suite.json', json.dumps(suite, indent=2) + '\n')
    save()
    images = prepare_images()
    for scenario, expected in SCENARIOS.items():
        result = run_demo(folder / scenario, scenario, images=images)
        suite['scenarios'].append({'scenario': scenario, 'expected': expected, 'actual': result['status'],
                                   'cleanup': result['cleanup']['status'], 'source_cleanup': result['source_cleanup']['status'],
                                   'matched_expected_cause': matches_scenario(scenario, result),
                                   'report_path': result['report_path'], 'source_report_path': result['source_report_path']})
        save()
        if result.get('error_type') == 'KeyboardInterrupt':
            suite['status'] = 'INCOMPLETE'
            save()
            return suite
    matched = all(item['matched_expected_cause'] for item in suite['scenarios'])
    suite['status'] = 'PASS' if matched else 'FAIL'
    save()
    return suite
