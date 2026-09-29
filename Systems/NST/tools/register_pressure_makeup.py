#!/usr/bin/env python3
"""Explicit config-only adoption of reviewed 507 baseline; never install/restart."""
import copy
import json
import socket
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, '/usr/lib/neiro-nli')
from nli.layout import DEFAULT_CONFIG, DATA_DIR, STATE_DIR, target
from nli.manifest import MAKEUP_TARGET, validate
from nli.plugins import PressureMakeup
from nli.util import Error, atomic, digest, read_json, require


def register(root='/'):
    if str(root) == '/':
        require(socket.gethostname() == 'wirenboard-ABF62SL', 'Wrong controller hostname')
    config_path = target(root, DEFAULT_CONFIG)
    config_bytes = config_path.read_bytes()
    config = read_json(config_path)
    require((config.get('object'), config.get('role'), config.get('hostname')) ==
            ('05_31_Ivolga_13', 'boiler', 'wirenboard-ABF62SL'), 'Wrong boiler identity')
    require('hhm' in config['components'] and 'pressure_makeup' not in config['components'],
            'Expected existing HHM and not-yet-registered pressure_makeup')
    require(not target(root, STATE_DIR + '/pending.json').exists(), 'Resolve pending transaction first')
    require(not target(root, STATE_DIR + '/pressure_makeup.json').exists(), 'Existing pressure_makeup state')
    example = read_json(target(root, DATA_DIR + '/examples/config-boiler.json'))
    registration = copy.deepcopy(example['components']['pressure_makeup'])
    raw = target(root, DATA_DIR + '/examples/pressure-makeup-boiler-1.0.json').read_bytes()
    require(digest(raw) == registration['baseline']['sha256'] == registration['target']['sha256'], 'Manifest checksum mismatch')
    manifest = validate(read_json(target(root, DATA_DIR + '/examples/pressure-makeup-boiler-1.0.json')))
    PressureMakeup().validate(manifest, registration)
    require(digest(target(root, MAKEUP_TARGET).read_bytes()) == manifest['files'][0]['sha256'],
            'Live 507 differs from reviewed baseline 1.0; do not auto-trust')
    for entry in config['components'].values():
        approved = entry.get('unmanaged_rules', {})
        if MAKEUP_TARGET in approved:
            require(approved[MAKEUP_TARGET] == manifest['files'][0]['sha256'], 'Reviewed 507 hash conflict')
            del approved[MAKEUP_TARGET]
    pin_path = target(root, registration['baseline']['path'])
    require(not pin_path.exists() or pin_path.read_bytes() == raw, 'Existing manifest differs')
    config['components']['pressure_makeup'] = registration
    # All guards precede writes; the original config is the last file replaced.
    # Run with other NLI/config editors idle. Recheck before committing the edit.
    require(config_path.read_bytes() == config_bytes, 'Config changed during adoption')
    backup = config_path.with_name('config.before-pressure-makeup-' + uuid.uuid4().hex + '.json')
    meta = config_path.stat()
    atomic(backup, config_bytes, 0o600, (meta.st_uid, meta.st_gid))
    atomic(pin_path, raw, 0o644)
    atomic(config_path, (json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode(),
           meta.st_mode & 0o777, (meta.st_uid, meta.st_gid))
    return backup


if __name__ == '__main__':
    try:
        print('Config backup: ' + str(register()))
        print('Registered pressure_makeup 1.0; run nli check hhm, then nli check pressure_makeup')
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        print('FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
