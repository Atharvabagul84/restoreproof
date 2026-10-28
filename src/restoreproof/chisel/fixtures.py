"""Synthetic identities and business records; seeded through Chisel's HTTP API."""
from datetime import datetime, timezone
import uuid
from .contract import canonical_sha256


def draft():
    return {'id': str(uuid.uuid4()), 'note': 'Prove that a team can recover and continue editing its feature briefs.',
            'spec': {'title': 'Recovery acceptance brief', 'problem': 'Backups do not prove application recovery.',
                     'targetUser': 'Platform engineer', 'successMetric': 'All required recovery journeys pass.',
                     'inScope': ['Recover a saved brief and accept a new edit.'], 'outOfScope': ['External AI generation.'],
                     'userStories': [{'id': 'US-1', 'persona': 'a team owner', 'goal': 'recover a saved brief',
                                      'benefit': 'the team can resume delivery'}],
                     'acceptanceCriteria': [{'id': 'AC-1', 'given': 'a recovered workspace',
                                             'when': 'the owner creates a brief', 'then': 'the saved brief can be read'}],
                     'assumptions': ['Recovery runs with isolated dependencies.'], 'openQuestions': [], 'risks': []},
            'source': 'manual', 'model': None, 'generatedAt': None,
            'updatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'revision': 0, 'checkedIds': []}


def _successful(response, status):
    if response['status'] != status:
        raise RuntimeError(f'Source fixture request returned HTTP {response["status"]}, expected {status}.')
    return response['body']


def seed(client):
    client.login('owner@restoreproof.test')
    workspace = _successful(client.request('POST', '/api/team/workspaces', {'name': 'Recovery acceptance'}), 201)['id']
    record = draft()
    _successful(client.request('POST', f'/api/team/workspaces/{workspace}/briefs',
                               {'draft': record, 'expectedRevision': 0}), 200)
    detail = _successful(client.request('GET', f'/api/team/workspaces/{workspace}'), 200)
    saved = next(item for item in detail['briefs'] if item['id'] == record['id'])
    owner = next(member['userId'] for member in detail['members'] if member['email'] == 'owner@restoreproof.test')
    outsider = client.clone()
    outsider.login('outsider@restoreproof.test')
    other_workspace = _successful(outsider.request('POST', '/api/team/workspaces', {'name': 'Private other team'}), 201)['id']
    return {'owner_id': owner, 'workspace_id': workspace, 'outsider_workspace_id': other_workspace,
            'brief_id': record['id'], 'brief_sha256': canonical_sha256(saved['draft'])}
