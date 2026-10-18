#!/usr/bin/env python3
"""Which manuals use which Python modules of shared/.

A change to a shared module rebuilds only the manuals that use it (build.yml),
and only those lose their compiled cache (native_cache.py). A manual uses the
modules its own scripts import or run, those of the common build pipeline,
and, in turn, theirs. Other shared files (styles, scripts, TeX files) count
for every manual, and so does a module that no manual is found to use.

  scripts/dependencies.py affected < changed-paths   # JSON list of manuals
  scripts/dependencies.py uses <package>              # its shared modules
"""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
# run for every manual
PIPELINE = ['scripts/build.sh', 'scripts/prepare.py', 'scripts/native_cache.py',
            '.github/workflows/build-package.yml']
IMPORT = re.compile(r'^\s*(?:from|import)\s+([A-Za-z_]\w*)', re.M)
SCRIPT = re.compile(r'\b([A-Za-z_]\w*)\.py\b')


def packages():
    return sorted(p.parent.name for p in ROOT.glob('*/upstream.lock'))


def module_files(name, root=ROOT):
    """The files of a shared module (texhtml is a package)."""
    shared = root / 'shared'
    if (shared / name / '__init__.py').is_file():
        return sorted(p for p in (shared / name).rglob('*.py') if '__pycache__' not in p.parts)
    path = shared / f'{name}.py'
    return [path] if path.is_file() else []


def names(paths, root=ROOT):
    """Modules imported, and scripts run (name.py), by these files. In the
    pipeline's and the shared Python files, only imports count (they name other
    files, such as native_cache.py's list of front-end files)."""
    found = set()
    for path in paths:
        text = path.read_text(errors='replace')
        found.update(IMPORT.findall(text))
        if path.suffix != '.py' or path.parent.parent == root and path.parent.name not in ('scripts', 'shared'):
            found.update(SCRIPT.findall(text))
    return found


def uses(package, root=ROOT):
    """The shared Python files that the build of a manual reads."""
    own = [p for p in (root / package).glob('*') if p.suffix in ('.py', '.sh')]
    todo = names(own + [root / p for p in PIPELINE if (root / p).is_file()], root)
    seen, files = set(), set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        new = set(module_files(name, root)) - files
        files |= new
        todo |= names(new, root)
    return {p.relative_to(root).as_posix() for p in files}


def affected(changed):
    """The manuals to rebuild for changed repository paths."""
    everything = packages()
    users = {package: uses(package) for package in everything}
    result = set()
    for path in changed:
        top = path.split('/')[0]
        if top in everything:
            result.add(top)
        elif top == 'shared' and path.endswith('.py'):
            using = {package for package, files in users.items() if path in files}
            result |= using or set(everything)
        elif top in ('shared', 'scripts', '.github'):
            result |= set(everything)
    return sorted(result)


if __name__ == '__main__':
    if sys.argv[1:2] == ['affected']:
        print(json.dumps(affected([line.strip() for line in sys.stdin if line.strip()])))
    elif sys.argv[1:2] == ['uses'] and len(sys.argv) == 3:
        print('\n'.join(sorted(uses(sys.argv[2]))))
    else:
        sys.exit(__doc__)
