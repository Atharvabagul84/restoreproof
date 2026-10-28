"""Append run evidence and update bounded history with conditional S3 writes."""
import json
from pathlib import Path
import re

from botocore.exceptions import BotoCoreError, ClientError

from .history import MAX_HISTORY_BYTES, merge_history, summarize
from ..contract import _reject_constant, _unique_contract_object, parse_timestamp

PREFIX = 'evidence/chisel/'


class PublicationError(RuntimeError):
    """Safe publication failure: never includes upstream response contents."""


def _json(data):
    if len(data) > MAX_HISTORY_BYTES:
        raise ValueError('Evidence exceeds bound.')
    return json.loads(data, parse_constant=_reject_constant, object_pairs_hook=_unique_contract_object)


def _validate_history(history):
    if history.get('schema_version') != 1 or not isinstance(history.get('recent_runs'), list) or len(history['recent_runs']) > 100:
        raise ValueError('Invalid history schema.')
    entries = history['recent_runs'] + [history.get('latest_attempt'), history.get('last_success')]
    for item in entries:
        if item is None:
            continue
        if (not re.fullmatch(r'[0-9a-f]{32}', item['run_id'])
                or item['status'] not in {'PASS', 'FAIL', 'INVALID', 'INCOMPLETE'}
                or item['cleanup_status'] not in {'PASS', 'INCOMPLETE', 'NOT_REQUIRED'}):
            raise ValueError('Invalid history entry.')
        parse_timestamp(item['started_at'])
    success = history.get('last_success')
    if success and (success['status'] != 'PASS' or success['cleanup_status'] != 'PASS'):
        raise ValueError('Invalid last success.')
    return history


def _read_history(client, request):
    response = client.get_object(**request)
    body = response['Body']
    try:
        if response['ContentLength'] > MAX_HISTORY_BYTES:
            raise ValueError('History exceeds bound.')
        history = _validate_history(_json(body.read(MAX_HISTORY_BYTES + 1)))
        etag = response['ETag']
        if not isinstance(etag, str) or not etag:
            raise ValueError('History lacks a concurrency token.')
        return history, etag
    finally:
        body.close()


def _encode(payload):
    data = (json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode()
    if len(data) > MAX_HISTORY_BYTES:
        raise ValueError('Encoded evidence exceeds bound.')
    return data


def publish_report(client, report_path, *, bucket, expected_bucket_owner):
    """The recovery role writes evidence only, and never uploads/deletes backups."""
    try:
        with Path(report_path).open('rb') as stream:
            report = _json(stream.read(MAX_HISTORY_BYTES + 1))
        if report.get('role') != 's3-recovery':
            raise ValueError('Not an S3 recovery report.')
        entry = summarize(report)
        # Local paths are not useful in cloud history; only retain relative evidence identities.
        report.pop('report_path', None)
        if 'application_recovery' in report:
            report['application_recovery'].pop('report_path', None)
        base = dict(Bucket=bucket, ExpectedBucketOwner=expected_bucket_owner)
        options = dict(ContentType='application/json', ServerSideEncryption='AES256')
        client.put_object(**base, **options, Key=PREFIX + 'runs/' + entry['run_id'] + '.json',
                          Body=_encode(report), IfNoneMatch='*')
        request = {**base, 'Key': PREFIX + 'history.json'}
        # Without ListBucket, GET of an absent index can return AccessDenied on AWS.
        # Conditional creation handles absence without overwriting or broadening IAM.
        try:
            client.put_object(**request, **options, IfNoneMatch='*',
                              Body=_encode({'schema_version': 1, 'recent_runs': []}))
        except ClientError as error:
            if error.response.get('Error', {}).get('Code') not in {'PreconditionFailed', '412'}:
                raise
        for _ in range(3):
            previous, etag = _read_history(client, request)
            history = merge_history(previous, entry)
            condition = {'IfMatch': etag} if etag else {'IfNoneMatch': '*'}
            try:
                client.put_object(**request, **options, **condition, Body=_encode(history))
                return history
            except ClientError as error:
                if error.response.get('Error', {}).get('Code') not in {'PreconditionFailed', 'ConditionalRequestConflict', '409', '412'}:
                    raise
        raise PublicationError('Evidence written, but concurrent history update did not complete.')
    except PublicationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, BotoCoreError, ClientError, RecursionError):
        raise PublicationError('S3 evidence publication incomplete; retained local report remains authoritative.') from None
