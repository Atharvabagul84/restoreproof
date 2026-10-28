"""Identify the executed Python source even from an uncommitted working tree."""
import hashlib
from pathlib import Path

from .. import __version__


def implementation():
    root = Path(__file__).resolve().parents[1]
    files = list(root.rglob('*.py')) + [root / 'chisel/assets/source-manifest.json']
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {'package_version': __version__, 'source_sha256': digest.hexdigest()}
