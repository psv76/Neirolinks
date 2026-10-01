#!/usr/bin/env python3
"""Prepare verified platform assets from an immutable main commit; never publish."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nst.controller import ControllerRegistry, validate_profile
from nst.deployment import verify_offline
from nst.releases import software_version
from nst.util import decode, require
from tools.build_deployment import git_blob, resolve, encode, APPROVALS_PATH
from tools.verify_approved_components import verify_data


def build(repo, commit, release_version, output):
    software_version(release_version)
    require(len(commit) == 40 and all(c in '0123456789abcdef' for c in commit), 'Immutable commit required')
    subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', commit, 'origin/main'], check=True)
    registry_raw = git_blob(repo, commit, 'Systems/NST/generated/controller-registry.json')
    registry = ControllerRegistry(decode(registry_raw))
    approvals = git_blob(repo, commit, APPROVALS_PATH)
    verify_data(decode(approvals))
    assets = {'nst-controller-registry.json': registry_raw}
    for serial, entry in registry.data['controllers'].items():
        if entry['state'] != 'active':
            continue
        raw = git_blob(repo, commit, entry['profile'])
        profile = validate_profile(decode(raw), serial)
        for key in ('name', 'node', 'role', 'state', 'capabilities', 'diagnostics_profile', 'fingerprint_sha256'):
            require(entry.get(key) == profile.get(key), 'Registry/profile mismatch: ' + key)
        required = set(profile['capabilities']) & {'hhm', 'pressure_makeup'}
        require(required <= set(profile.get('components', {})),
                'Missing approved desired components for ' + serial + ': ' + ', '.join(sorted(required-set(profile.get('components', {})))))
        read_blob = lambda c, p: git_blob(repo, c, p)
        deployment = resolve(serial, commit, entry['profile'], raw, approvals, read_blob)
        deployment['minimum_nst'] = '2.0'
        for component in deployment['components']:
            software_version(component['version'])
        verify_offline(deployment, read_blob)
        assets['nst-deployment-' + serial + '.json'] = encode(deployment)
    require(len(assets) > 1, 'No active deployment assets')
    output.mkdir(parents=True, exist_ok=True)
    for name, data in assets.items():
        (output / name).write_bytes(data)
    metadata = {'schema': 1, 'source_commit': commit, 'tag': 'nst-approved-platform-' + release_version,
                'minimum_nst': '2.0', 'assets': {n: hashlib.sha256(b).hexdigest() for n,b in assets.items()}}
    (output / 'nst-platform-metadata.json').write_bytes(encode(metadata))
    return metadata


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--commit', required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(ROOT.parents[1], a.commit, a.version, a.output), indent=2))
