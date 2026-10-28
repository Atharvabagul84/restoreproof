"""RestoreProof command line; JSON summaries and stable verification exit codes."""

import argparse
import json
from pathlib import Path

from . import __version__
from .contract import APPROVED_IMAGE
from .engine import verify


def _parser():
    parser = argparse.ArgumentParser(prog='restoreproof', description='Verify application recovery in disposable PostgreSQL targets.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    from .s3.cli import register
    register(commands)
    html_report = commands.add_parser('report-html', help='Export retained S3 recovery journals as one offline HTML report')
    html_report.add_argument('--input', action='append', type=Path, required=True, help='Report file or directory; repeat to compare storage scopes')
    html_report.add_argument('--output', type=Path, required=True, help='Destination .html file')
    commands.add_parser('prepare-app', help='Build pinned Chisel app and recovery dependencies')
    app_demo = commands.add_parser('app-demo', help='Capture and recover the real Chisel application')
    app_demo.add_argument('--scenario', choices=['healthy', 'missing-data', 'incompatible-schema',
                                                'auth-unavailable', 'missing-config', 'all'], default='healthy')
    app_demo.add_argument('--output', type=Path, default=Path('runs/chisel'))
    app_verify = commands.add_parser('verify-app', help='Verify a trusted Chisel recovery contract')
    app_verify.add_argument('contract', type=Path)
    app_verify.add_argument('--output', type=Path, default=Path('runs/chisel'))
    app_cleanup = commands.add_parser('cleanup-app', help='Recover cleanup for an exact application run ID')
    app_cleanup.add_argument('run_id')
    verification = commands.add_parser('verify', help='Restore and verify a trusted JSON contract')
    verification.add_argument('contract', type=Path)
    verification.add_argument('--output', type=Path, default=Path('runs'))
    demo = commands.add_parser('demo', help='Create and verify a synthetic backup')
    demo.add_argument('--scenario', choices=['healthy', 'stale', 'inconsistent', 'corrupt',
                                            'ledger-healthy', 'ledger-gap', 'application', 'application-broken'], default='healthy')
    demo.add_argument('--output', type=Path, default=Path('runs'))
    demo.add_argument('--image', default=APPROVED_IMAGE)
    cleanup = commands.add_parser('cleanup', help='Recover cleanup for an exact RestoreProof run ID')
    cleanup.add_argument('run_id')
    cleanup.add_argument('--image', default=APPROVED_IMAGE)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == 'report-html':
            from .reporting.export import write_html
            try:
                print(json.dumps(write_html(args.input, args.output)))
                return 0
            except ValueError as error:
                print(json.dumps({'export_status': 'INVALID', 'message': str(error)}))
                return 3
        if args.command in {'verify-s3', 's3-demo', 's3-history'}:
            from .s3.cli import execute
            return execute(args)
        if args.command in {'prepare-app', 'app-demo', 'verify-app', 'cleanup-app'}:
            return _application_command(args)
        if args.command == 'cleanup':
            from .docker_postgres import DockerPostgres
            outcome = DockerPostgres.cleanup_run(args.image, args.run_id)
            print(json.dumps(outcome))
            return 0 if outcome['status'] == 'PASS' else 2
        contract = args.contract if args.command == 'verify' else None
        if args.command == 'demo':
            from .demo import create_demo
            contract = create_demo(args.output, args.scenario, args.image)
        report = verify(contract, args.output)
        print(json.dumps({
            'status': report['status'], 'exit_code': report['exit_code'],
            'run_id': report['run_id'], 'report_path': report['report_path'],
            'contract_path': str(contract.resolve()), 'cleanup': report['cleanup']['status'],
        }))
        return report['exit_code']
    except ValueError:
        print(json.dumps({'status': 'INVALID', 'message': 'Invalid run ID, image or configuration.'}))
        return 3
    except (Exception, KeyboardInterrupt) as error:
        from .demo import DemoError
        message = str(error) if isinstance(error, DemoError) else f'Command incomplete ({type(error).__name__}).'
        print(json.dumps({'status': 'INCOMPLETE', 'message': message}))
        return 2


def _application_command(args):
    if args.command == 'prepare-app':
        from .chisel.images import prepare_images
        print(json.dumps({'status': 'PASS', 'images': prepare_images()}))
        return 0
    if args.command == 'cleanup-app':
        from .chisel.stack import cleanup_run
        result = cleanup_run(args.run_id)
        print(json.dumps(result))
        return 0 if result['status'] == 'PASS' else 2
    if args.command == 'app-demo':
        from .chisel.demo import run_demo, run_suite
        if args.scenario == 'all':
            result = run_suite(args.output)
            print(json.dumps(result))
            from .engine import EXIT_CODES
            return EXIT_CODES[result['status']]
        result = run_demo(args.output, args.scenario)
    else:
        from .chisel.runner import verify_app
        result = verify_app(args.contract, args.output)
    print(json.dumps({key: result[key] for key in ('status', 'exit_code', 'run_id', 'report_path', 'cleanup')}))
    return result['exit_code']
