"""Free ephemeral S3 lab, isolated to one uniquely named bucket on loopback."""
from contextlib import contextmanager
import logging
import uuid

from botocore.exceptions import ClientError

from .client import create_client


@contextmanager
def local_storage():
    from moto.server import ThreadedMotoServer
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = ThreadedMotoServer(ip_address='127.0.0.1', port=0, verbose=False)
    server.start()
    client = create_client(endpoint=f'http://127.0.0.1:{server.get_host_and_port()[1]}')
    bucket = 'restoreproof-lab-' + uuid.uuid4().hex
    state = {'client': client, 'bucket': bucket, 'cleanup': 'INCOMPLETE'}
    created = False
    try:
        client.create_bucket(Bucket=bucket)
        created = True
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={'Status': 'Enabled'})
        yield state
    finally:
        try:
            if created:
                # Only this function's freshly created local bucket is eligible for deletion.
                client.delete_bucket_policy(Bucket=bucket)
                versions = client.list_object_versions(Bucket=bucket)
                if versions.get('IsTruncated'):
                    raise RuntimeError('Lab cleanup inventory unexpectedly exceeds one page.')
                objects = [{'Key': item['Key'], 'VersionId': item['VersionId']}
                           for item in versions.get('Versions', []) + versions.get('DeleteMarkers', [])]
                if objects:
                    result = client.delete_objects(Bucket=bucket, Delete={'Objects': objects, 'Quiet': True})
                    if result.get('Errors'):
                        raise RuntimeError('Lab object cleanup incomplete.')
                client.delete_bucket(Bucket=bucket)
                try:
                    client.head_bucket(Bucket=bucket)
                except ClientError as error:
                    if error.response.get('ResponseMetadata', {}).get('HTTPStatusCode') != 404:
                        raise
                else:
                    raise RuntimeError('Lab bucket still exists.')
            state['cleanup'] = 'PASS'
        finally:
            client.close()
            server.stop()
