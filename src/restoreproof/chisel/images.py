"""Verify the source snapshot and build content-addressed local lab images."""
import hashlib
import json
from .assets import ASSETS
from .contract import SOURCE_COMMIT
from ..process import ProcessError, run_command


def verify_source():
    manifest = json.loads((ASSETS / 'source-manifest.json').read_text(encoding='utf-8'))
    if manifest['commit'] != SOURCE_COMMIT:
        raise ValueError('Unexpected Chisel source revision.')
    root = ASSETS / 'app'
    actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in root.rglob('*') if p.is_file()}
    if actual != manifest['files']:
        raise ValueError('Chisel source differs from its pinned manifest.')
    return manifest


def asset_digest():
    digest = hashlib.sha256()
    for path in sorted(p for p in ASSETS.rglob('*') if p.is_file()):
        digest.update(path.relative_to(ASSETS).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def prepare_images():
    verify_source()
    images = json.loads((ASSETS / 'images.json').read_text(encoding='utf-8'))
    for name, ref in tuple(images.items()):
        try:
            run_command(['docker', 'image', 'inspect', ref])
        except ProcessError:
            run_command(['docker', 'pull', ref], timeout=600, max_output=4*1024*1024)
        if name != 'database':
            images[name] = json.loads(run_command(['docker', 'image', 'inspect', ref]))[0]['Id']
    digest = asset_digest()
    for component in ('gateway', 'app'):
        tag = f'restoreproof/chisel-{component}:{digest[:20]}'
        try:
            item = json.loads(run_command(['docker', 'image', 'inspect', tag]))[0]
            if item.get('Config', {}).get('Labels', {}).get('io.restoreproof.assets') != digest:
                raise ValueError('Local image provenance does not match the asset bundle.')
        except ProcessError:
            run_command(['docker', 'build', '--label', 'io.restoreproof.assets=' + digest,
                         '--label', 'io.restoreproof.chisel_commit=' + SOURCE_COMMIT,
                         '-t', tag, '-f', str(ASSETS / f'Dockerfile.{component}'), str(ASSETS)],
                        timeout=900, max_output=8*1024*1024)
            item = json.loads(run_command(['docker', 'image', 'inspect', tag]))[0]
        images[component] = item['Id']
    return images
