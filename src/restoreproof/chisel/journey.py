"""Real application acceptance checks, without SQL as an application substitute."""
from .contract import canonical_sha256
from .fixtures import draft
from .client import DependencyUnavailable

REQUIRED_CHECKS = frozenset({'unauthenticated-denied', 'email-otp-login', 'restored-identity',
                             'saved-brief-content', 'recovered-write-cycle', 'tenant-isolation', 'signout'})


def _check(name, success, **evidence):
    return {'name': name, 'status': 'PASS' if success else 'FAIL', **evidence}


def _write_cycle(client, base):
    record = draft()
    written = client.request('POST', base + '/briefs', {'draft': record, 'expectedRevision': 0})
    evidence = {'create_http': written['status']}
    if written['status'] != 200:
        return _check('recovered-write-cycle', False, **evidence, failed_stage='create')
    saved = written['body']['brief']
    readback = client.request('GET', base)
    found = next((item for item in readback['body'].get('briefs', []) if item['id'] == record['id']), None)
    evidence['read_http'] = readback['status']
    if not found or found != saved:
        return _check('recovered-write-cycle', False, **evidence, failed_stage='readback')
    changed = {**saved['draft'], 'note': 'An edit after disaster recovery must retain optimistic concurrency.'}
    updated = client.request('POST', base + '/briefs', {'draft': changed, 'expectedRevision': saved['revision']})
    if updated['status'] != 200:
        return _check('recovered-write-cycle', False, **evidence, failed_stage='update', update_http=updated['status'])
    stale = client.request('POST', base + '/briefs', {'draft': saved['draft'], 'expectedRevision': saved['revision']})
    final = client.request('GET', base)
    final_brief = next((item for item in final['body'].get('briefs', []) if item['id'] == record['id']), None)
    same = final_brief == updated['body']['brief']
    return _check('recovered-write-cycle', stale['status'] == 409 and same,
                  **evidence, update_http=updated['status'], stale_write_http=stale['status'],
                  stale_write_left_content_unchanged=same, brief_id=record['id'])


def run_journey(client, contract, record):
    """Append each completed check immediately; preserve partial evidence on errors."""
    response = client.request('GET', '/api/team/workspaces')
    record(_check('unauthenticated-denied', response['status'] == 401, http=response['status']))
    try:
        client.login('owner@restoreproof.test')
    except DependencyUnavailable as error:
        record({'name': 'email-otp-login', 'status': 'INCOMPLETE', 'http': error.http_status,
                'reason': 'Application authentication dependency did not complete.'})
        raise
    record(_check('email-otp-login', True, transport='TLS; certificate verified', session='HTTP-only secure cookies'))
    base = f'/api/team/workspaces/{contract.workspace_id}'
    response = client.request('GET', base)
    detail = response['body'] if isinstance(response['body'], dict) else {}
    same_owner = any(item['userId'] == contract.owner_id and item['email'] == 'owner@restoreproof.test'
                     and item['role'] == 'owner' for item in detail.get('members', []))
    record(_check('restored-identity', response['status'] == 200 and same_owner,
                  http=response['status'], owner_id=contract.owner_id))
    brief = next((item for item in detail.get('briefs', []) if item['id'] == contract.brief_id), None)
    actual = canonical_sha256(brief['draft']) if brief else None
    record(_check('saved-brief-content', actual == contract.brief_sha256,
                  expected_sha256=contract.brief_sha256, actual_sha256=actual, brief_id=contract.brief_id))
    record(_write_cycle(client, base))
    isolated = client.request('GET', f'/api/team/workspaces/{contract.outsider_workspace_id}')
    record(_check('tenant-isolation', isolated['status'] == 404, http=isolated['status']))
    signed_out = client.request('POST', '/api/auth/signout', {})
    after = client.request('GET', '/api/team/workspaces')
    record(_check('signout', signed_out['status'] == 200 and after['status'] == 401,
                  signout_http=signed_out['status'], afterwards_http=after['status']))
