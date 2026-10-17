"""Content-based asset URLs, including for multiple deployments on one day."""
import hashlib
from pathlib import Path


def asset_url(name, root='.'):
    version = hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()[:12]
    return f'{name}?v={version}'
