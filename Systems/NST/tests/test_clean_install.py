"""Independent pristine-root deployment and transaction failure scenarios."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_core import FakeSystem
from test_desired_state import DesiredStateTests, Source, registry
from nst.controller import ControllerRegistry, read_hardware_identity
from nst.core import Engine
from nst.desired import DesiredState
from nst.layout import CONFIG_DIR, DEFAULT_CONFIG, STATE_DIR, load_config
from nst.transaction import DeploymentTransaction
from nst.util import Error, digest, write_json


class CleanInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.system = FakeSystem()
        serial = self.root / 'var/lib/wirenboard/short_sn'
        serial.parent.mkdir(parents=True)
        serial.write_text('ABCDE\n')
        identity = read_hardware_identity(self.root)
        controller = ControllerRegistry({'schema': 1, 'controllers': {}}).resolve(identity)
        config = dict(object='unconfigured', role='unconfigured', hostname='unconfigured', components={})
        self.engine = Engine(config, self.root, self.system)
        self.engine.controller = controller
        self.manifest = dict(schema=1, component='demo', version='2.0', object='test', role='boiler',
            release=dict(repository='psv76/Neirolinks', commit='a'*40),
            files=[dict(source='demo/data.json', target='/etc/neirolinks/components/demo/data.json', sha256=digest(b'new'))],
            services=dict(stop=[], start=[]), preflight=['identity', 'drift'],
            verify=dict(controls=[], runtime_version='2.0', health_contract='none'), rollback='previous-managed-release')
        self.deployment = DesiredStateTests.deployment(self, self.manifest)
        self.deployment['minimum_nst'] = '2.0'
        self.deployment['object_files'] = [dict(source='Objects/test/hello.js', target='/etc/wb-rules/hello.js',
                                                 sha256=digest(b'// reviewed rule\n'))]
        self.deployment['services'] = dict(stop=['wb-rules'], start=['wb-rules'])
        self.source = Source(self.deployment, self.manifest)
        self.engine.releases = self
        self.payload_calls = []

    def fetch(self, url, *args):
        self.payload_calls.append(url)
        return b'// reviewed rule\n' if url.endswith('hello.js') else b'new'

    def sync(self):
        return DesiredState(self.engine, self.source).sync()

    def test_pristine_root_serial_registry_bootstrap_check_sync_and_restart(self):
        self.assertFalse(self.engine.target(CONFIG_DIR).exists())
        self.assertEqual(self.engine.controller['state'], 'unknown')
        result = DesiredState(self.engine, self.source).check()
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertFalse(self.payload_calls)
        self.assertFalse(self.engine.target(CONFIG_DIR).exists())
        result = self.sync()
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(result['plan']['status'], 'exact')
        self.assertFalse(self.engine.target('/mnt/data/etc/neiro/nli').exists())
        config = load_config(root=self.root)
        restarted = Engine(config, self.root, self.system, self, self.engine.controller)
        status = DesiredState(restarted, self.source).status()
        self.assertEqual(status['final_status'], 'ok', status)
        self.assertEqual(status['deployment_state']['status'], 'exact')
        self.assertEqual(DesiredState(restarted, self.source).check()['plan']['status'], 'exact')

    def test_unknown_writer_refused_before_services(self):
        p = self.engine.target('/etc/wb-rules/unknown.js')
        p.parent.mkdir(parents=True)
        p.write_bytes(b'// unknown')
        result = self.sync()
        self.assertEqual(result['final_status'], 'failed', result)
        self.assertIn('Unknown possible writer', result['error'])
        self.assertFalse(self.system.actions)
        self.assertFalse(self.engine.target(DEFAULT_CONFIG).exists())

    def test_object_checksum_refused_before_services(self):
        self.deployment['object_files'][0]['sha256'] = '0'*64
        result = self.sync()
        self.assertEqual(result['final_status'], 'failed', result)
        self.assertFalse(self.system.actions)

    def test_service_failure_rolls_back_new_files_and_config(self):
        self.system.failures = ['start']
        result = self.sync()
        self.assertEqual(result['final_status'], 'rolled_back', result)
        for p in (DEFAULT_CONFIG, '/etc/wb-rules/hello.js', self.manifest['files'][0]['target']):
            self.assertFalse(self.engine.target(p).exists(), p)
        self.assertFalse(self.engine.pending())

    def test_object_runtime_error_rolls_back(self):
        self.system.logs = 'SyntaxError in hello.js'
        result = self.sync()
        self.assertEqual(result['final_status'], 'rolled_back', result)
        self.assertFalse(self.engine.target('/etc/wb-rules/hello.js').exists())

    def test_interrupted_restore_retains_intent_and_explicit_recovery(self):
        self.system.failures = ['start']
        with patch.object(DeploymentTransaction, '_restore', side_effect=OSError('interrupted')):
            result = self.sync()
        self.assertEqual(result['final_status'], 'recovery_required', result)
        self.assertTrue(self.engine.pending())
        self.assertEqual(self.sync()['final_status'], 'failed')
        recovered = DeploymentTransaction(self.engine).recover()
        self.assertEqual(recovered['final_status'], 'ok')
        self.assertFalse(self.engine.pending())
        self.assertFalse(self.engine.target(DEFAULT_CONFIG).exists())

    def test_fingerprint_mismatch_is_readonly(self):
        original = self.source.latest
        def latest(serial):
            approved = original(serial)
            approved['registry']['controllers'][serial]['fingerprint_sha256'] = '9'*64
            return approved
        self.source.latest = latest
        result = self.sync()
        self.assertEqual(result['final_status'], 'failed')
        self.assertFalse(self.engine.target(STATE_DIR).exists())

    def test_low_disk_space_is_refused_before_service_actions(self):
        with patch('nst.transaction.shutil.disk_usage', return_value=shutil._ntuple_diskusage(10, 10, 0)):
            result = self.sync()
        self.assertEqual(result['final_status'], 'failed', result)
        self.assertFalse(self.system.actions)


if __name__ == '__main__':
    unittest.main()
