"""Bounded streaming download; verified bytes are atomically published."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
import time

from botocore.exceptions import BotoCoreError, ClientError

from ..contract import MAX_ARCHIVE_BYTES


class RetrievalError(RuntimeError):
    def __init__(self, code, status='INCOMPLETE'):
        self.code, self.status = code, status
        super().__init__(code)


def _stream(body, path, expected_size, expected_hash, deadline):
    digest, size = hashlib.sha256(), 0
    with path.open('wb') as stream:
        while True:
            if time.monotonic() > deadline:
                raise RetrievalError('download-timeout')
            chunk = body.read(64 * 1024)
            if time.monotonic() > deadline:
                raise RetrievalError('download-timeout')
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise RetrievalError('archive-too-large', 'FAIL')
            if size > expected_size:
                raise RetrievalError('size-mismatch', 'FAIL')
            stream.write(chunk)
            digest.update(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    if size != expected_size:
        raise RetrievalError('size-mismatch', 'FAIL')
    if digest.hexdigest() != expected_hash:
        raise RetrievalError('checksum-mismatch', 'FAIL')
    return size


def retrieve(client, spec, destination, *, now=None):
    """No list/latest lookup, ETag-as-hash shortcut, or fallback to another version."""
    now = now or datetime.now(timezone.utc)
    age = (now - spec.captured_at).total_seconds()
    if age < 0:
        raise RetrievalError('future-backup', 'INVALID')
    if age > spec.max_age_seconds:
        raise RetrievalError('stale-backup', 'FAIL')
    destination = Path(destination)
    if destination.exists():
        raise RetrievalError('destination-exists', 'INVALID')
    body, temporary = None, None
    deadline = time.monotonic() + 60
    try:
        response = client.get_object(Bucket=spec.bucket, Key=spec.key, VersionId=spec.version_id,
                                     ExpectedBucketOwner=spec.expected_bucket_owner)
        body = response['Body']
        if response.get('VersionId') != spec.version_id or response.get('DeleteMarker'):
            raise RetrievalError('version-mismatch', 'FAIL')
        size = response.get('ContentLength')
        if type(size) is not int or size <= 0:
            raise RetrievalError('invalid-content-length', 'FAIL')
        if size > MAX_ARCHIVE_BYTES:
            raise RetrievalError('archive-too-large', 'FAIL')
        descriptor, name = tempfile.mkstemp(prefix='.s3-download-', dir=destination.parent)
        os.close(descriptor)
        temporary = Path(name)
        size = _stream(body, temporary, size, spec.sha256, deadline)
        # Close transport before publishing; close failures cannot leave a verified destination.
        body.close()
        body = None
        os.replace(temporary, destination)
        modified = response.get('LastModified')
        return {**spec.model_dump(mode='json'), 'size_bytes': size, 'age_seconds': round(age, 6),
                'verified_at': now.isoformat(),
                'object_last_modified': modified.isoformat() if isinstance(modified, datetime) else None}
    except ClientError as error:
        upstream = error.response.get('Error', {}).get('Code')
        code = {'NoSuchKey': 'missing-object', 'NoSuchVersion': 'missing-object',
                'NoSuchBucket': 'missing-object', 'AccessDenied': 'access-denied',
                '403': 'access-denied'}.get(upstream, 's3-request-failed')
        raise RetrievalError(code) from None
    except (BotoCoreError, ConnectionError, TimeoutError, KeyboardInterrupt):
        raise RetrievalError('download-interrupted') from None
    finally:
        try:
            if body is not None:
                body.close()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
