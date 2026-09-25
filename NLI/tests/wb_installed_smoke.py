"""Run only in the disposable CI container; exercise INSTALLED modules/data."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

assert os.environ.get('NLI_DISPOSABLE_CI') == '1' and Path('/.dockerenv').exists()
sys.dont_write_bytecode = True
sys.path.insert(0, '/usr/lib/neiro-nli')
import nli
from nli.core import Engine
from nli.layout import CONFIG_DIR, DEFAULT_CONFIG, DATA_DIR, STATE_DIR, LOG_DIR, load_config
from nli.util import digest, read_json, write_json
assert nli.__version__ == '0.1.9'
assert nli.__file__.startswith('/usr/lib/neiro-nli/')
assert Path('/usr/share/neiro-nli/RECOVERY.md').is_file()


class FakeWB:
    """No subprocess, systemctl, MQTT publish, serial or hardware operations."""
    def __init__(self):
        self.actions = []

    def hostname(self):
        return 'wirenboard-ABF62SL'

    def service(self, action, name):
        assert name == 'wb-rules'
        self.actions.append((action, name))

    def active(self, name):
        pass

    def rules_version(self):
        return '2.46.5'

    def control(self, path, timeout=None):
        return '0' if path == 'A04/K1' or (path.startswith('pressure_makeup/') and not path.endswith('last_event')) else 'OK'

    def rule_started(self, marker, since=None):
        pass

    def mqtt(self, topic, fresh=False, timeout=None):
        assert fresh
        return json.dumps(dict(sent_ms=time.time() * 1000, source='ivolga-hhm3-house', v=3, seq=1))

    def journal(self, since=None):
        return ''


def snapshot():
    return {str(p): [digest(p.read_bytes()), p.stat().st_mode, p.stat().st_uid, p.stat().st_gid]
            for p in Path('/mnt/data').rglob('*') if p.is_file()}


def readonly(engine, pending=False):
    before = snapshot()
    status = engine.read_operation('status')
    assert status['final_status'] == ('recovery_required' if pending else 'ok'), status
    for component in ('hhm', 'pressure_makeup'):
        for command in ('check', 'verify'):
            r = engine.read_operation(command, component)
            assert r['final_status'] == ('failed' if pending else 'ok'), r
    cli = subprocess.run(['/usr/bin/nli', '--json', 'status'], capture_output=True, text=True)
    assert cli.returncode == (1 if pending else 0), cli.stdout + cli.stderr
    assert json.loads(cli.stdout)['object'] == '05_31_Ivolga_13'
    assert before == snapshot(), 'Read-only command changed persistent bytes/metadata'


mode = sys.argv[1]
if mode == 'bootstrap':
    for name in ('manifest.schema.json', 'WB_SMOKE.md', 'PRESSURE_MAKEUP.md', 'register_pressure_makeup.py',
                 'examples/config-boiler.json', 'examples/pressure-makeup-boiler-1.0.json', 'examples/hhm-boiler-3.0.json'):
        assert (Path(DATA_DIR) / name).is_file(), name
    assert not Path('/usr/share/doc/neiro-nli/README.md').exists(), 'nodoc policy not exercised'
    config = read_json(Path(DATA_DIR) / 'examples/config-boiler.json')
    assert (config['object'], config['role'], config['hostname']) == (
        '05_31_Ivolga_13', 'boiler', 'wirenboard-ABF62SL')
    r = config['components']['hhm']
    assert r['baseline'] == r['target'] and r['unmanaged_rules'] == {}
    manifest_bytes = (Path(DATA_DIR) / 'examples/hhm-boiler-3.0.json').read_bytes()
    assert digest(manifest_bytes) == r['target']['sha256']
    manifest = json.loads(manifest_bytes)
    for folder in ('wb-rules', 'wb-rules-modules'):
        Path('/mnt/data/etc', folder).mkdir(parents=True)
        Path('/etc', folder).symlink_to('/mnt/data/etc/' + folder, target_is_directory=True)
    # Only synthetic CI rootfs. Exact Git bytes supplied by a read-only fixture mount.
    for f in manifest['files']:
        data = (Path('/payload') / f['source']).read_bytes()
        assert digest(data) == f['sha256']
        Path(f['target']).write_bytes(data)
    Path(r['target']['path']).parent.mkdir(parents=True)
    Path(r['target']['path']).write_bytes(manifest_bytes)
    shutil.copytree('/payload', '/mnt/data/neiro/ci-payload')
    r['payload_dir'] = '/mnt/data/neiro/ci-payload'  # offline test fixture, never bypass SHA
    makeup = config['components'].pop('pressure_makeup')
    makeup_raw = (Path(DATA_DIR) / 'examples/pressure-makeup-boiler-1.0.json').read_bytes()
    makeup_manifest = json.loads(makeup_raw)
    f = makeup_manifest['files'][0]
    makeup_bytes = (Path(DATA_DIR) / 'payload' / f['source']).read_bytes()
    assert digest(makeup_bytes) == f['sha256']
    Path(f['target']).write_bytes(makeup_bytes)
    r['unmanaged_rules'][f['target']] = f['sha256']
    # Upgrade an existing reviewed 0.1.1 config using the installed config-only helper.
    write_json(Path(DEFAULT_CONFIG), config)
    subprocess.run(['/usr/bin/python3', '-B', DATA_DIR + '/register_pressure_makeup.py'], check=True)
    config = load_config()
    config['release_source'] = 'pinned'
    assert config['components']['pressure_makeup'] == makeup
    r = config['components']['hhm']
    assert f['target'] not in r['unmanaged_rules']
    engine = Engine(load_config(), system=FakeWB())
    readonly(engine)
    assert not Path(STATE_DIR).exists() and not Path(LOG_DIR).exists()
    unknown = Path('/etc/wb-rules/unknown-rule.js')
    unknown.write_bytes(b"defineVirtualDevice('ci-other-device', {}); // no physical controls")
    failed = engine.read_operation('check', 'hhm')
    assert failed['final_status'] == 'failed' and 'possible writer' in failed['error'], failed
    assert not Path(STATE_DIR).exists() and not Path(LOG_DIR).exists()
    r['unmanaged_rules'][str(unknown)] = digest(unknown.read_bytes())
    write_json(Path(DEFAULT_CONFIG), config)
    engine = Engine(load_config(), system=FakeWB())  # next CLI invocation reloads reviewed config
    original_control = engine.system.control
    readiness_reads = []
    def delayed_control(path, timeout=None):
        if path == 'HHM3_FSE/runtime_status':
            readiness_reads.append(path)
            if len(readiness_reads) == 1:
                return 'STARTUP'
        return original_control(path, timeout=timeout)
    for component in ('hhm', 'pressure_makeup'):
        for command in ('update', 'rollback'):
            readiness_reads.clear()
            with patch.object(engine.system, 'journal', return_value='ERROR on device ci-other-device: Control already exists'), \
                 patch.object(engine.system, 'control', side_effect=delayed_control):
                result = engine.mutate(command, component)
            assert result['final_status'] == 'ok', result
            assert result['verification_attempts'][0]['journal'][0]['category'] == 'shared_runtime', result
        assert Path(f['target']).read_bytes() == makeup_bytes
    assert digest(unknown.read_bytes()) == r['unmanaged_rules'][str(unknown)]
    # Manually deployed exact 3.1 must be recognized by the installed package offline.
    known = read_json(Path(DATA_DIR) / 'known/hhm-boiler-3.1.json')
    old = {item['target']: Path(item['target']).read_bytes() for item in known['files']}
    for item in known['files']:
        Path(item['target']).write_bytes((Path('/payload31') / item['source']).read_bytes())
    before = snapshot()
    assert engine.read_operation('status')['components']['hhm']['manifest']['version'] == '3.1'
    verified = engine.read_operation('verify', 'hhm')
    assert verified['final_status'] == 'ok' and verified['from_version'] == '3.1', verified
    assert snapshot() == before
    for path, data in old.items():
        Path(path).write_bytes(data)  # synthetic fixture only; restore prior test state
    # Simulate crash/failed rollback: a reinstall must preserve pending recovery.
    with patch.object(engine, 'install', side_effect=OSError('simulated storage interruption')):
        result = engine.mutate('update', 'hhm')
    assert result['final_status'] == 'partial_failure', result
    readonly(engine, pending=True)
    # Real dpkg self-update/retry in this disposable container, component pending preserved.
    from nli.self_update import SelfUpdate
    from nli.system import System
    package_data = Path('/packages/neiro-nli_0.1.9_all.deb').read_bytes()
    class ApprovedPackage:
        def package(self):
            return dict(version='0.1.9', sha256=digest(package_data), approved=True, asset={'id': 1})
        def asset(self, *args):
            return package_data
    engine.releases = ApprovedPackage()
    engine.system.run = System().run  # only package-manager/version commands, no WB probes
    saved_pending = engine.pending_path.read_bytes()
    write_json(engine.target(STATE_DIR + '/self-update.json'), {'to_version': '0.1.9'})
    upgraded = SelfUpdate(engine).execute()
    assert upgraded['final_status'] == 'ok', upgraded
    assert engine.pending_path.read_bytes() == saved_pending
    assert not list(engine.state_dir.glob('nli-package-*'))
    print('SELF-UPDATE: actual dpkg same-version recovery, CLI version, preserved component pending PASS')
    Path('/evidence/persistent.json').write_text(json.dumps(snapshot()), encoding='utf-8')
    print('INSTALLED BOILER: two components, config migration, exact 507, canonical links, read-only, strict inventory, independent update/rollback, pending PASS')
elif mode in ('reinstall', 'fit'):
    assert snapshot() == read_json('/evidence/persistent.json'), 'Package changed durable data'
    if mode == 'fit':
        for folder in ('wb-rules', 'wb-rules-modules'):
            Path('/etc', folder).symlink_to('/mnt/data/etc/' + folder, target_is_directory=True)
    engine = Engine(load_config(), system=FakeWB())
    readonly(engine, pending=True)
    status = engine.read_operation('status')
    assert status['components']['hhm']['manifest']['version'].startswith('3.0.0-FSE')
    assert status['last_operations']['hhm']['final_status'] == 'partial_failure'
    engine.load_backup(status['pending']['backup'], 'hhm')
    if mode == 'fit':
        result = engine.mutate('rollback', 'hhm')
        assert result['final_status'] == 'ok', result
        readonly(engine)
    print(mode.upper() + ': config/pins/state/backups/pending/audit preserved; recovery PASS')
else:
    raise AssertionError(mode)
