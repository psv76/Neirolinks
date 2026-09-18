"""Offline installer smoke test. Run from a checkout; NEVER touches a real controller."""
import importlib.util
import pathlib
import tempfile
import sys
import shutil

release = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer', str(release / 'install_hm2_iset_51.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
# Supply reviewed candidate and original trees from a checked-out fixture/previous live archive.
# Set HM2_TEST_FIXTURES=/absolute/path/to/fixtures (original/, candidate/, modules/, floor_only.patch).
import os
fixtures = pathlib.Path(os.environ['HM2_TEST_FIXTURES'])
orig = fixtures / 'original'
candidate = fixtures / 'candidate'
modules = fixtures / 'modules'
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    m.RULES = root / 'etc/wb-rules'
    m.MODULES = root / 'etc/wb-rules-modules'
    m.DATA = root / 'mnt/data'
    m.RULES.mkdir(parents=True)
    m.MODULES.mkdir(parents=True)
    m.DATA.mkdir(parents=True)
    for n in m.NAMES:
        shutil.copyfile(str(orig / n), str(m.RULES / n))
    for n in m.MODULE_SHA:
        shutil.copyfile(str(modules / n), str(m.MODULES / n))
    service = {'running': True, 'fail_start': False}
    def system(cmd, check=True):
        if cmd[:2] == ['systemctl', 'is-active']:
            return type('Result', (), {'stdout': 'active\n' if service['running'] else 'inactive\n'})()
        if cmd[:2] == ['systemctl', 'stop']:
            service['running'] = False
        if cmd[:2] == ['systemctl', 'start']:
            if service['fail_start']:
                service['fail_start'] = False
                raise RuntimeError('simulated restart failure')
            service['running'] = True
        return type('Result', (), {'stdout': 'ok\n'})()
    m.run = system
    m.fetch = lambda path, expected: (fixtures / 'floor_only.patch').read_bytes() if path.endswith('.patch') else (candidate / pathlib.Path(path).name).read_bytes()
    m.shutil.which = lambda name: None
    sys.argv = ['installer']
    m.main()
    assert all((m.RULES / n).read_bytes() == (orig / n).read_bytes() for n in m.NAMES)
    print('PASS preflight leaves originals unchanged')
    sys.argv = ['installer', '--apply', '--confirm']
    m.main()
    assert all((m.RULES / n).read_bytes() == (candidate / n).read_bytes() for n in m.NAMES)
    assert list((m.DATA / 'hm2_backups').glob('*.tar.gz'))
    print('PASS apply with backup and unchanged source manager')
    for n in m.NAMES:
        shutil.copyfile(str(orig / n), str(m.RULES / n))
    service['fail_start'] = True
    try:
        m.main()
    except RuntimeError as exc:
        assert 'simulated restart failure' in str(exc)
    else:
        raise AssertionError('restart failure not detected')
    assert service['running']
    assert all((m.RULES / n).read_bytes() == (orig / n).read_bytes() for n in m.NAMES)
    print('PASS rollback restores original files')
    (m.RULES / m.NAMES[0]).write_bytes(b'drift')
    try:
        m.main()
    except RuntimeError as exc:
        assert 'Live drift' in str(exc)
    else:
        raise AssertionError('live drift not detected')
    assert service['running']
    print('PASS live drift stops preflight')
print('OFFLINE TESTS: 4 PASS, not a real controller test')
