"""Real installed package in disposable clean rootfs; fake engineering backend."""
import os
from pathlib import Path
import sys

assert os.environ.get('NST_DISPOSABLE_CI') == '1' and Path('/.dockerenv').exists()
sys.path.insert(0, '/usr/lib/nst')
import nst
assert nst.__file__.startswith('/usr/lib/nst/nst/') and nst.__version__ == '2.0'
from nst.core import Engine
from nst.layout import load_config
from nst.controller import load_controller_context
from test_clean_install import CleanInstallTests

test = CleanInstallTests('test_pristine_root_serial_registry_bootstrap_check_sync_and_restart')
test.setUp()
try:
    p = Path('/var/lib/wirenboard/short_sn')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('ABCDE\n')
    test.root = Path('/')
    test.engine = Engine(load_config(), '/', test.system, test, load_controller_context())
    test.test_pristine_root_serial_registry_bootstrap_check_sync_and_restart()
    print('CLEAN INSTALL: installed nst, hardware identity, registry/deployment, config, components/object files, status/check PASS')
finally:
    test.doCleanups()
