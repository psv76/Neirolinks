"""Offline installer regression. No MQTT, systemctl, or /etc writes."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
from unittest.mock import patch

object_dir = Path(__file__).resolve().parent.parent
wrapper = (object_dir / 'tools/hm2_install_cold_slab_v2.sh').read_text(encoding='utf-8')
program = wrapper.split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
compile(program, '<installer>', 'exec')
names = ['501_tp_dom_manager.js', '502_gp_dom_manager.js', '620_thermostats.js']
fake_fcntl = types.SimpleNamespace(LOCK_EX=1, LOCK_NB=2, flock=lambda *a: None)
checks = 0

with tempfile.TemporaryDirectory(prefix='hm2-installer-test-') as tmp:
    base = Path(tmp)
    live = base / 'live'
    backups = base / 'backups'
    live.mkdir()
    for name in names:
        source = object_dir / 'Wirenboard/wb-rules' / name
        (live / name).write_bytes(source.read_bytes() + b'\n// original live file\n')
    originals = {n: (live / n).read_bytes() for n in names}
    code = program.replace("Path('/etc/wb-rules')", "Path(" + repr(str(live)) + ")")
    code = code.replace("Path('/root/hm2/backups')", "Path(" + repr(str(backups)) + ")")
    code = code.replace("'/run/lock/hm2-cold-slab-v2.lock'", repr(str(base / 'lock')))
    writes = []
    nonzero = False

    def fake_run(args, **kwargs):
        assert args[0] in ('systemctl', 'mosquitto_pub'), args
        if args[0] == 'mosquitto_pub':
            assert args[-1] == '0', args
            assert any(d in args[2] for d in ('hm2_501_tp_dom', 'hm2_502_gp_dom'))
            writes.append(args)
        return types.SimpleNamespace(returncode=0)

    def fake_get(args, **kwargs):
        assert args[0] == 'mosquitto_sub'
        return '1' if nonzero and args[-1].endswith('/K1') else '0'

    def execute(mode, src):
        with patch.dict(sys.modules, {'fcntl': fake_fcntl}), \
             patch.object(sys, 'argv', ['installer', mode, str(src)]), \
             patch('subprocess.run', fake_run), patch('subprocess.check_output', fake_get), \
             patch('time.sleep', lambda *a: None):
            namespace = {}
            try:
                exec(compile(code, '<installer-test>', 'exec'), namespace)
            finally:
                if 'lock' in namespace:
                    namespace['lock'].close()

    execute('install', object_dir)
    assert all((live / n).read_bytes() == (object_dir / 'Wirenboard/wb-rules' / n).read_bytes() for n in names)
    saved = next(backups.iterdir())
    assert all((saved / n).read_bytes() == originals[n] for n in names)
    assert writes
    checks += 1
    print('PASS installer backup, exact replacement and zero-only disarm')

    execute('rollback', saved)
    assert all((live / n).read_bytes() == originals[n] for n in names)
    checks += 1
    print('PASS rollback restores original live files without arming')

    before = len(writes)
    corrupt = base / 'corrupt'
    corrupt.mkdir()
    (corrupt / 'sha256.json').write_text(json.dumps({n: 'bad' for n in names}))
    for n in names:
        shutil.copy2(saved / n, corrupt / n)
    try:
        execute('rollback', corrupt)
        raise AssertionError('Corrupt package was accepted')
    except SystemExit as error:
        assert 'Checksum mismatch' in str(error)
    assert len(writes) == before
    assert all((live / n).read_bytes() == originals[n] for n in names)
    checks += 1
    print('PASS checksum failure before physical actions or file replacement')

    nonzero = True
    try:
        execute('install', object_dir)
        raise AssertionError('Nonzero physical output was accepted')
    except RuntimeError as error:
        assert 'Nonzero output' in str(error)
    assert all((live / n).read_bytes() == originals[n] for n in names)
    checks += 1
    print('PASS nonzero readback blocks installation')

print('Installer checks:', checks)
