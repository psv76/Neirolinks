"""Independent 507 transactions and cross-component ownership, fake WB only."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_nli as fixtures
from nli.core import Engine
from nli.layout import CONFIG_DIR, STATE_DIR, LOG_DIR, WB_ROOTS, target
from nli.manifest import MAKEUP_TARGET, validate
from nli.plugins import PressureMakeup
from nli.util import Error, digest

ROOT = Path(__file__).resolve().parents[1]


class MakeupSystem(fixtures.FakeSystem):
    def __init__(self):
        super().__init__()
        self.started = []
        self.controls.update({'pressure_makeup/' + x: '0' for x in (
            'valve_open', 'sensor_alarm', 'low_pressure_alarm', 'makeup_failed_alarm', 'watchdog_alarm', 'pulse_count')})
        self.controls.update({'pressure_makeup/enabled': '1', 'pressure_makeup/auto_mode': '1',
                              'pressure_makeup/last_event': 'Инициализация: клапан закрыт'})

    def rule_started(self, marker, since=None):
        self.started.append((marker, since))


class PressureFixture(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        self.component = 'pressure_makeup'
        self.system = MakeupSystem()
        self.config.update(object='05_31_Ivolga_13', components={})
        self.hhm = fixtures.HHMTests.hhm_manifest(self, 'boiler')
        for f in self.hhm['files']:
            data = b"version:'3.0.0-FSE'" if f['target'].endswith('HHM3Config.js') else b'// rule'
            self.put(f['target'], data)
            self.put('/opt/payload/' + f['source'], data)
        self.config['components']['hhm'] = dict(plugin='hhm',
            baseline=self.pin(CONFIG_DIR + '/hhm-base.json', self.hhm),
            target=self.pin(CONFIG_DIR + '/hhm-target.json', self.hhm), payload_dir='/opt/payload', unmanaged_rules={})
        self.base = json.loads((ROOT / 'examples/pressure-makeup-boiler-1.0.json').read_bytes())
        self.old_bytes = (ROOT.parent / self.base['files'][0]['source']).read_bytes()
        self.new = copy.deepcopy(self.base)
        self.new.update(version='1.1')
        self.new['verify']['runtime_version'] = '1.1'
        self.new_bytes = self.old_bytes + b'\n// synthetic release for transaction tests\n'
        self.new['files'][0]['sha256'] = digest(self.new_bytes)
        self.put(MAKEUP_TARGET, self.old_bytes)
        self.put('/opt/payload/' + self.base['files'][0]['source'], self.new_bytes)
        self.config['components'][self.component] = dict(plugin=self.component,
            baseline=self.pin(CONFIG_DIR + '/makeup-base.json', self.base),
            target=self.pin(CONFIG_DIR + '/target.json', self.new), payload_dir='/opt/payload')
        self.engine = Engine(self.config, self.root, self.system)

    def put(self, path, data):
        p = target(self.root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def hhm_bytes(self):
        return {f['target']: self.engine.target(f['target']).read_bytes() for f in self.hhm['files']}


class PressureTests(PressureFixture):
    def test_exact_baseline_readonly_commands_no_state_or_logs(self):
        r = self.config['components'][self.component]
        r['target'] = r['baseline']
        self.put('/opt/payload/' + self.base['files'][0]['source'], self.old_bytes)
        before = self.snapshot()
        for component in ('hhm', 'pressure_makeup'):
            for command in ('check', 'verify'):
                result = self.engine.read_operation(command, component)
                self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.engine.target(STATE_DIR).exists())
        self.assertFalse(self.engine.target(LOG_DIR).exists())
        self.assertEqual(self.system.actions, [])

    def test_update_verify_rollback_only_507(self):
        before = self.hhm_bytes()
        r = self.engine.mutate('update', self.component)
        self.assertEqual(r['final_status'], 'ok', r)
        self.assertEqual(self.engine.target(MAKEUP_TARGET).read_bytes(), self.new_bytes)
        self.assertEqual(self.engine.current(self.component)['version'], '1.1')
        meta, _ = self.engine.load_backup(r['backup'], self.component)
        self.assertEqual([f['target'] for f in meta['files']], [MAKEUP_TARGET])
        self.assertEqual(self.engine.read_operation('verify', self.component)['final_status'], 'ok')
        r = self.engine.mutate('rollback', self.component)
        self.assertEqual(r['final_status'], 'ok', r)
        self.assertEqual(self.engine.target(MAKEUP_TARGET).read_bytes(), self.old_bytes)
        self.assertEqual(before, self.hhm_bytes())
        self.assertFalse(self.engine.state_path('hhm').exists())
        self.assertEqual(self.system.actions, [('stop','wb-rules'),('start','wb-rules')] * 2)

    def test_hhm_update_rollback_preserve_managed_507_and_use_installed_peer(self):
        self.assertEqual(self.engine.mutate('update', self.component)['final_status'], 'ok')
        before = self.engine.state_path(self.component).read_bytes()
        r = self.engine.mutate('update', 'hhm')
        self.assertEqual(r['final_status'], 'ok', r)
        meta, _ = self.engine.load_backup(r['backup'], 'hhm')
        self.assertNotIn(MAKEUP_TARGET, {f['target'] for f in meta['files']})
        self.assertEqual(self.engine.mutate('rollback', 'hhm')['final_status'], 'ok')
        self.assertEqual(self.engine.target(MAKEUP_TARGET).read_bytes(), self.new_bytes)
        self.assertEqual(before, self.engine.state_path(self.component).read_bytes())

    def test_drift_507_blocks_both_components_before_services(self):
        self.put(MAKEUP_TARGET, self.old_bytes + b'\n')  # even final LF is real drift
        for component in ('hhm', self.component):
            r = self.engine.mutate('update', component)
            self.assertEqual(r['final_status'], 'failed', r)
            self.assertIn('drift', r['error'])
            self.assertIsNone(r['backup'])
        self.assertEqual(self.system.actions, [])

    def test_missing_peer_and_bad_peer_pin_not_auto_trusted(self):
        self.config['components'][self.component]['baseline']['sha256'] = '0' * 64
        self.assertIn('checksum', self.engine.read_operation('check','hhm')['error'])
        self.config['components'][self.component]['baseline'] = self.pin(CONFIG_DIR+'/makeup-base.json',self.base)
        self.engine.target(MAKEUP_TARGET).unlink()
        self.assertIn('drift', self.engine.read_operation('check','hhm')['error'])

    def test_managed_unmanaged_conflict_requires_explicit_migration(self):
        self.config['components']['hhm']['unmanaged_rules'][MAKEUP_TARGET] = digest(self.old_bytes)
        self.assertIn('ownership conflict', self.engine.read_operation('check','hhm')['error'])

    def test_unknown_other_writer_still_blocks_both(self):
        self.put('/etc/wb-rules/evil.js', b"dev['A04/K1']=true")
        for c in ('hhm',self.component):
            self.assertIn('possible writer', self.engine.read_operation('check',c)['error'])

    def test_hhm_cannot_claim_507_or_output(self):
        m = copy.deepcopy(self.hhm)
        m['files'].append(self.base['files'][0])
        with self.assertRaises(Error):
            self.engine.validate(m,'hhm')
        m = copy.deepcopy(self.hhm)
        m['outputs'] = ['A04/K1']
        with self.assertRaises(Error):
            self.engine.validate(m,'hhm')
        _, files, outputs = self.engine.ownership(self.hhm)
        self.assertEqual(files[MAKEUP_TARGET],self.component)
        self.assertEqual(outputs['A04/K1'],self.component)

    def test_wrong_role_payload_services_and_policy_rejected(self):
        for change in ('role','files','services','plugin','alias'):
            with self.subTest(change=change):
                m=copy.deepcopy(self.base)
                if change=='role': m['role']='gazebo'
                if change=='files': m['files'].append(self.hhm['files'][0])
                if change=='services': m['services']={'stop':['wb-mqtt-serial'],'start':['wb-mqtt-serial']}
                if change=='plugin':
                    self.config['components'][self.component]['plugin']='files'
                if change=='alias': m['component']='other_makeup'
                with self.assertRaises(Error): self.engine.validate(m,self.component)
                self.config['components'][self.component]['plugin']=self.component

    def test_preflight_off_interlocks_not_pressure_or_alarm_gate(self):
        self.system.controls.update({'pressure_makeup/pressure_bar':'0','pressure_makeup/sensor_alarm':'1',
                                     'pressure_makeup/pulse_count':'5','pressure_makeup/watchdog_alarm':'1'})
        self.assertEqual(self.engine.read_operation('check',self.component)['final_status'],'ok')
        for path in ('pressure_makeup/active','A04/K1'):
            for value in ('1','','unknown'):
                self.system.controls[path]=value
                r=self.engine.mutate('update',self.component)
                self.assertEqual(r['final_status'],'failed')
                self.assertEqual(self.system.actions,[])
            self.system.controls[path]='0'

    def test_restart_resets_runtime_and_normal_evaluate_on_is_accepted(self):
        self.system.controls.update({'pressure_makeup/pulse_count':'5','pressure_makeup/watchdog_alarm':'1'})
        original=self.system.service
        def restart(action,name):
            original(action,name)
            if action=='start':
                self.system.controls.update({'pressure_makeup/pulse_count':'0','pressure_makeup/watchdog_alarm':'0',
                    'pressure_makeup/active':'1','pressure_makeup/valve_open':'1','A04/K1':'1'})
        self.system.service=restart
        r=self.engine.mutate('update',self.component)
        self.assertEqual(r['final_status'],'ok',r)
        self.assertTrue(self.system.started[0][1])
        self.assertEqual(self.system.controls['pressure_makeup/pulse_count'],'0')
        self.assertEqual(self.system.controls['A04/K1'],'1')

    def test_startup_missing_and_runtime_errors_fail_verify(self):
        with patch.object(self.system,'rule_started',side_effect=Error('Missing rule startup marker')):
            self.assertEqual(self.engine.read_operation('verify',self.component)['final_status'],'failed')
        for path in ('pressure_makeup/active','pressure_makeup/pulse_count','pressure_makeup/last_event'):
            old=self.system.controls[path]
            self.system.controls[path]=''
            self.assertEqual(self.engine.read_operation('verify',self.component)['final_status'],'failed')
            self.system.controls[path]=old
        self.system.logs='ReferenceError: pressure_makeup'
        self.assertEqual(self.engine.read_operation('verify',self.component)['final_status'],'failed')

    def test_failed_verify_rolls_back_only_pressure(self):
        before=self.hhm_bytes()
        with patch.object(self.system,'rule_started',side_effect=[Error('startup failed'),None]):
            r=self.engine.mutate('update',self.component)
        self.assertEqual(r['final_status'],'rolled_back',r)
        self.assertEqual(self.engine.target(MAKEUP_TARGET).read_bytes(),self.old_bytes)
        self.assertEqual(before,self.hhm_bytes())

    def test_partial_install_recovery_allows_missing_507_but_checks_peer(self):
        original=self.engine.install
        called=[]
        def interrupted(*args):
            called.append(1)
            if len(called)==1:
                self.engine.target(MAKEUP_TARGET).unlink()
                raise OSError('interrupted replacement')
            return original(*args)
        with patch.object(self.engine,'install',side_effect=interrupted):
            r=self.engine.mutate('update',self.component)
        self.assertEqual(r['final_status'],'rolled_back',r)
        self.assertEqual(self.engine.target(MAKEUP_TARGET).read_bytes(),self.old_bytes)


class PressureWBTests(PressureTests):
    """The entire component/ownership suite also runs with canonical WB links."""
    def setUp(self):
        super().setUp()
        for alias,persistent in WB_ROOTS.items():
            link=self.root/alias.lstrip('/')
            real=self.root/persistent.lstrip('/')
            real.parent.mkdir(parents=True,exist_ok=True)
            link.rename(real)
            try: link.symlink_to(persistent,target_is_directory=True)
            except OSError:
                self.temp.cleanup()
                self.skipTest('Canonical WB symlinks require Linux or symlink privilege')
