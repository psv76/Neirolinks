"""Config-only migration preserves existing reviewed policies, never live deploy."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_pressure_makeup as pressure
from nli.layout import CONFIG_DIR, DEFAULT_CONFIG, DATA_DIR, STATE_DIR, LOG_DIR
from nli.manifest import MAKEUP_TARGET
from nli.system import System
from nli.util import Error, digest, read_json


class BootstrapTests(pressure.PressureFixture):
    def setUp(self):
        super().setUp()
        self.config['hostname']='wirenboard-ABF62SL'
        del self.config['components']['pressure_makeup']
        self.config['components']['hhm']['unmanaged_rules']={MAKEUP_TARGET:digest(self.old_bytes),
            '/etc/wb-rules/other-reviewed.js':'a'*64}
        self.config['firmware']={'approved_package_version':'keep-existing-setting'}
        self.put(DEFAULT_CONFIG,json.dumps(self.config).encode())
        for name in ('config-boiler.json','pressure-makeup-boiler-1.0.json'):
            self.put(DATA_DIR+'/examples/'+name,(pressure.ROOT/'examples'/name).read_bytes())
        spec=importlib.util.spec_from_file_location('register_pressure_makeup',pressure.ROOT/'tools/register_pressure_makeup.py')
        self.tool=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def test_migration_preserves_hhm_other_reviewed_entries_and_backup(self):
        old=self.engine.target(DEFAULT_CONFIG).read_bytes()
        hhm=self.hhm_bytes()
        backup=self.tool.register(self.root)
        new=read_json(self.engine.target(DEFAULT_CONFIG))
        expected=copy.deepcopy(self.config)
        del expected['components']['hhm']['unmanaged_rules'][MAKEUP_TARGET]
        expected['components']['pressure_makeup']=read_json(self.engine.target(DATA_DIR+'/examples/config-boiler.json'))['components']['pressure_makeup']
        self.assertEqual(new,expected)
        self.assertEqual(backup.read_bytes(),old)
        self.assertEqual(self.hhm_bytes(),hhm)
        self.assertEqual(self.engine.target(MAKEUP_TARGET).read_bytes(),self.old_bytes)
        self.assertFalse(self.engine.target(STATE_DIR).exists())
        self.assertFalse(self.engine.target(LOG_DIR).exists())
        before=self.snapshot()
        with self.assertRaises(Error): self.tool.register(self.root)
        self.assertEqual(before,self.snapshot())

    def test_drift_and_reviewed_hash_mismatch_refuse_without_writes(self):
        self.put(MAKEUP_TARGET,self.old_bytes+b'\n')
        before=self.snapshot()
        with self.assertRaisesRegex(Error,'differs'): self.tool.register(self.root)
        self.assertEqual(before,self.snapshot())
        self.put(MAKEUP_TARGET,self.old_bytes)
        self.config['components']['hhm']['unmanaged_rules'][MAKEUP_TARGET]='0'*64
        self.put(DEFAULT_CONFIG,json.dumps(self.config).encode())
        before=self.snapshot()
        with self.assertRaisesRegex(Error,'hash conflict'): self.tool.register(self.root)
        self.assertEqual(before,self.snapshot())

    def test_pending_and_prior_state_block_registration(self):
        for name in ('pending.json','pressure_makeup.json'):
            p=self.put(STATE_DIR+'/'+name,b'{}')
            before=self.snapshot()
            with self.assertRaises(Error): self.tool.register(self.root)
            self.assertEqual(before,self.snapshot())
            p.unlink()

    def test_conflicting_pin_and_wrong_identity_do_not_overwrite(self):
        path=CONFIG_DIR+'/releases/pressure-makeup-boiler-1.0.json'
        p=self.put(path,b'{}')
        before=self.snapshot()
        with self.assertRaisesRegex(Error,'manifest differs'): self.tool.register(self.root)
        self.assertEqual(before,self.snapshot())
        p.unlink()
        self.config['role']='gazebo'
        self.put(DEFAULT_CONFIG,json.dumps(self.config).encode())
        before=self.snapshot()
        with self.assertRaisesRegex(Error,'identity'): self.tool.register(self.root)
        self.assertEqual(before,self.snapshot())


class StartupProbeTests(unittest.TestCase):
    def test_waits_for_delayed_marker_and_is_readonly(self):
        system=System()
        with patch.object(system,'journal',side_effect=['','startup-marker']) as journal, \
             patch('nli.system.time.sleep') as sleep:
            system.rule_started('startup-marker','start-time')
        self.assertEqual(journal.call_count,2)
        journal.assert_called_with('start-time')
        sleep.assert_called_once_with(0.5)

    def test_missing_marker_has_bounded_failure(self):
        system=System()
        with patch.object(system,'journal',return_value=''), \
             patch('nli.system.time.monotonic',side_effect=[0,16]):
            with self.assertRaisesRegex(Error,'Missing rule startup'): system.rule_started('marker', 'restart-time')
