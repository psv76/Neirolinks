#!/usr/bin/env python3
"""Build metadata for a maintainer-reviewed DRAFT release; never publish/deploy."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'Systems/NST'))
from nst.manifest import validate
from nst.releases import REPO, software_version as version


def build(commit, manifests, package, package_version, minimum_nst, output):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Full immutable catalog source commit required')
    version(minimum_nst)
    entries = []
    for path in manifests:
        data = subprocess.check_output(['git', '-C', str(ROOT), 'show', commit + ':' + path])
        m = validate(json.loads(data))
        version(m['version'])
        if m['release']['repository'] != REPO:
            raise ValueError('Foreign component repository')
        entries.append(dict(component=m['component'], object=m['object'], role=m['role'], version=m['version'],
                            approved=True, minimum_nst=minimum_nst,
                            manifest=dict(commit=commit, path=path, sha256=hashlib.sha256(data).hexdigest())))
    catalog = dict(schema=1, repository=REPO, approved=True, components=entries)
    if package:
        version(package_version)
        if package.name != 'nst_' + package_version + '_all.deb':
            raise ValueError('Package name/version mismatch')
        catalog['nst'] = dict(version=package_version, approved=True, sha256=hashlib.sha256(package.read_bytes()).hexdigest())
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--commit', required=True)
    p.add_argument('--manifest', action='append', default=[])
    p.add_argument('--package', type=Path)
    p.add_argument('--package-version', default='2.0')
    p.add_argument('--minimum-nst', default='2.0')
    p.add_argument('--output', type=Path, default=Path('nst-catalog.json'))
    args = p.parse_args()
    build(args.commit, args.manifest, args.package, args.package_version, args.minimum_nst, args.output)
