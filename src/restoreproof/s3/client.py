"""Explicit credentials and endpoints: local mode cannot discover AWS credentials."""
import os
import re
from urllib.parse import urlsplit

import boto3
from botocore.config import Config


def _local_endpoint(endpoint):
    if not isinstance(endpoint, str):
        raise ValueError('Local S3 requires an explicit loopback endpoint.')
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', '::1'}
            or not parsed.port or parsed.username or parsed.password
            or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
        raise ValueError('Local S3 requires a literal loopback HTTP endpoint and port.')
    return endpoint.rstrip('/')


def create_client(*, mode='local', endpoint=None, region='us-east-1'):
    if not re.fullmatch(r'[a-z]{2}-[a-z]+-[1-9]', region):
        raise ValueError('A commercial AWS region is required.')
    if mode == 'local':
        endpoint = _local_endpoint(endpoint)
        credentials = dict(aws_access_key_id='restoreproof-local', aws_secret_access_key='restoreproof-local')
    elif mode == 'aws':
        if endpoint is not None or os.environ.get('RESTOREPROOF_AWS_FREE_VERIFIED') != 'true':
            raise ValueError('AWS access requires verified free-only controls and no custom endpoint.')
        names = ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')
        if not all(os.environ.get(name) for name in names):
            raise ValueError('AWS mode requires explicit temporary session credentials.')
        credentials = dict(zip(('aws_access_key_id', 'aws_secret_access_key', 'aws_session_token'),
                               (os.environ[name] for name in names)))
        endpoint = f'https://s3.{region}.amazonaws.com'
    else:
        raise ValueError('Unknown storage mode.')
    session = boto3.session.Session(region_name=region, **credentials)
    client = session.client('s3', endpoint_url=endpoint, config=Config(
        signature_version='s3v4', connect_timeout=3, read_timeout=10,
        retries={'total_max_attempts': 1, 'mode': 'standard'}, proxies={},
        ignore_configured_endpoint_urls=True, s3={'addressing_style': 'path'}))
    selected = urlsplit(endpoint)

    def enforce_endpoint(request, **kwargs):
        actual = urlsplit(request.url)
        if (actual.scheme, actual.hostname, actual.port) != (selected.scheme, selected.hostname, selected.port):
            raise ValueError('S3 endpoint redirect refused.')

    client.meta.events.register('before-send.s3', enforce_endpoint)
    return client
