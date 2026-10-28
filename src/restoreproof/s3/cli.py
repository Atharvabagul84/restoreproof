"""Storage commands keep temporary cloud credentials out of arguments and reports."""
import json
from pathlib import Path

from .client import create_client
from .drill import run_drill
from .evidence import publish_report, PublicationError
from .history import read_history
from ..engine import EXIT_CODES
from ..reports import _atomic_write


def register(commands):
    verify = commands.add_parser('verify-s3', help='Recover Chisel from an exact versioned S3 backup')
    verify.add_argument('contract', type=Path)
    verify.add_argument('--output', type=Path, default=Path('runs/s3'))
    verify.add_argument('--mode', choices=['local', 'aws'], default='local')
    verify.add_argument('--endpoint', help='Required loopback endpoint in local mode; forbidden in AWS mode')
    verify.add_argument('--region', default='us-east-1')
    verify.add_argument('--publish', action='store_true', help='Publish evidence and history to the backup bucket')
    verify.add_argument('--summary', type=Path, help='Also write a stable path to the latest run summary')
    demo = commands.add_parser('s3-demo', help='Free local S3-to-Chisel recovery and five storage failure cases')
    demo.add_argument('--output', type=Path, default=Path('runs/s3-demo'))
    history = commands.add_parser('s3-history', help='Show local attempts and last successful recovery')
    history.add_argument('--output', type=Path, default=Path('runs/s3'))
    history.add_argument('--limit', type=int, default=30)


def execute(args):
    if args.command == 's3-history':
        print(json.dumps(read_history(args.output, limit=args.limit)))
        return 0
    if args.command == 's3-demo':
        from .demo import run_demo
        suite = run_demo(args.output)
        print(json.dumps(suite))
        return EXIT_CODES[suite['status']]
    client = create_client(mode=args.mode, endpoint=args.endpoint, region=args.region)
    try:
        report = run_drill(args.contract, args.output, client=client)
        summary = {key: report[key] for key in ('status', 'exit_code', 'run_id', 'report_path', 'cleanup')}
        summary.update(verification_status=report['status'], publication_status='NOT_REQUESTED')
        if args.publish:
            summary['publication_status'] = 'INCOMPLETE'
            try:
                if not report.get('backup'):
                    raise PublicationError('Invalid contract provides no trusted evidence destination.')
                history = publish_report(client, report['report_path'], bucket=report['backup']['bucket'],
                                         expected_bucket_owner=report['backup']['expected_bucket_owner'])
                summary.update(publication_status='PASS', last_success=history['last_success'])
            except PublicationError as error:
                summary.update(status='INCOMPLETE', exit_code=2, publication_error=str(error))
        payload = json.dumps(summary, indent=2) + '\n'
        _atomic_write(Path(report['report_path']).with_name('run-summary.json'), payload)
        if args.summary:
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(args.summary, payload)
        print(json.dumps(summary))
        return summary['exit_code']
    finally:
        client.close()
