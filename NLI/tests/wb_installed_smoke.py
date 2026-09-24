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
assert nli.__version__ == '0.1.2'
assert nli.__file__.startswith('/usr/lib/neiro-nli/')


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

    def control(self, path):
        return '0' if path == 'A04/K1' or (path.startswith('pressure_makeup/') and not path.endswith('last_event')) else 'OK'

    def rule_started(self, marker, since=None):
        pass

    def mqtt(self, topic, fresh=False):
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
    assert config['components']['pressure_makeup'] == makeup
    r = config['components']['hhm']
    assert f['target'] not in r['unmanaged_rules']
    engine = Engine(load_config(), system=FakeWB())
    readonly(engine)
    assert not Path(STATE_DIR).exists() and not Path(LOG_DIR).exists()
    unknown = Path('/etc/wb-rules/unknown-rule.js')
    unknown.write_bytes(b'// isolated CI fixture; no physical controls')
    failed = engine.read_operation('check', 'hhm')
    assert failed['final_status'] == 'failed' and 'possible writer' in failed['error'], failed
    assert not Path(STATE_DIR).exists() and not Path(LOG_DIR).exists()
    r['unmanaged_rules'][str(unknown)] = digest(unknown.read_bytes())
    write_json(Path(DEFAULT_CONFIG), config)
    engine = Engine(load_config(), system=FakeWB())  # next CLI invocation reloads reviewed config
    for component in ('hhm', 'pressure_makeup'):
        for command in ('update', 'rollback'):
            result = engine.mutate(command, component)
            assert result['final_status'] == 'ok', result
        assert Path(f['target']).read_bytes() == makeup_bytes
    assert digest(unknown.read_bytes()) == r['unmanaged_rules'][str(unknown)]
    # Simulate crash/failed rollback: a reinstall must preserve pending recovery.
    with patch.object(engine, 'install', side_effect=OSError('simulated storage interruption')):
        result = engine.mutate('update', 'hhm')
    assert result['final_status'] == 'partial_failure', result
    readonly(engine, pending=True)
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
