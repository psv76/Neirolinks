"""Bounded post-restart readiness with virtual time and fake WB only."""
import json
import subprocess
import unittest
from unittest.mock import patch

from test_pressure_makeup import PressureFixture
from nli.plugins import HHM
from nli.system import System
from nli.util import Error


class ReadinessTests(PressureFixture):
    def setUp(self):
        super().setUp()
        self.clock = 0.0
        self.sleeps = []
        self.addCleanup(patch.stopall)
        patch('nli.plugins.time.monotonic', side_effect=lambda: self.clock).start()
        patch('nli.plugins.time.sleep', side_effect=self.sleep).start()
        self.original_control = self.system.control

    def sleep(self, seconds):
        self.assertGreater(seconds, 0)
        self.sleeps.append(seconds)
        self.clock += seconds

    def delayed(self, seconds):
        def control(path, timeout=None):
            if path == 'HHM3_FSE/runtime_status' and self.clock < seconds:
                return 'STARTUP / Запуск'
            return self.original_control(path, timeout=timeout)
        return control

    def test_delayed_update_and_explicit_rollback(self):
        for command in ('update', 'rollback'):
            start = self.clock
            with patch.object(self.system, 'control', side_effect=self.delayed(start + 2)):
                r = self.engine.mutate(command, 'hhm')
            self.assertEqual(r['final_status'], 'ok', r)
            report = r['verification_attempts'][0]['readiness']
            self.assertEqual(report['status'], 'ready')
            self.assertEqual(report['elapsed_seconds'], 2)
            self.assertEqual(report['attempts'], 5)
            self.assertIsNone(self.engine.pending())

    def test_ready_first_attempt_has_no_sleep(self):
        r = self.engine.mutate('update', 'hhm')
        self.assertEqual(r['final_status'], 'ok', r)
        self.assertEqual(r['verification_attempts'][0]['readiness']['attempts'], 1)
        self.assertEqual(self.sleeps, [])

    def test_update_timeout_then_delayed_autorollback_recovers(self):
        with patch.object(self.system, 'control', side_effect=self.delayed(32)):
            r = self.engine.mutate('update', 'hhm')
        self.assertEqual(r['final_status'], 'rolled_back', r)
        attempts = r['verification_attempts']
        self.assertEqual([a['readiness']['status'] for a in attempts], ['timeout', 'ready'])
        self.assertEqual([a['readiness']['elapsed_seconds'] for a in attempts], [30, 2])
        self.assertIn('readiness timeout', r['error'])
        self.assertIn('HHM3_FSE/runtime_status', attempts[0]['readiness']['last_error'])
        self.assertIsNone(self.engine.pending())

    def test_timeout_both_attempts_preserves_pending_then_recovery_waits(self):
        with patch.object(self.system, 'control', side_effect=self.delayed(100)):
            failed = self.engine.mutate('update', 'hhm')
        self.assertEqual(failed['final_status'], 'partial_failure', failed)
        self.assertEqual(self.clock, 60)
        self.assertIsNotNone(self.engine.pending())
        with patch.object(self.system, 'control', side_effect=self.delayed(62)):
            result = self.engine.mutate('rollback', 'hhm')
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(result['backup'], failed['backup'])
        self.assertIsNone(self.engine.pending())

    def test_standalone_unhealthy_is_immediate_readonly_failure(self):
        before = self.snapshot()
        with patch.object(self.system, 'control', side_effect=self.delayed(2)):
            result = self.engine.read_operation('verify', 'hhm')
        self.assertEqual(result['final_status'], 'failed', result)
        self.assertEqual(self.sleeps, [])
        self.assertEqual(self.system.actions, [])
        self.assertEqual(self.snapshot(), before)

    def test_original_journal_boundary_still_fatal_after_wait(self):
        boundaries = []
        def journal(since):
            boundaries.append(since)
            return 'ERROR [500_HHM3_FSE] at startup' if len(boundaries) == 1 else ''
        with patch.object(self.system, 'control', side_effect=self.delayed(2)), \
             patch.object(self.system, 'journal', side_effect=journal):
            result = self.engine.mutate('update', 'hhm')
        self.assertEqual(result['final_status'], 'rolled_back', result)
        attempts = result['verification_attempts']
        self.assertEqual(boundaries, [a['since'] for a in attempts])
        self.assertEqual(attempts[0]['readiness']['elapsed_seconds'], 2)
        self.assertTrue(attempts[0]['journal'][0]['fatal'])
        self.assertNotEqual(boundaries[0], boundaries[1])

    def test_missing_malformed_stale_and_wrong_frame_never_pass(self):
        for frame in ('{', '{}', json.dumps(dict(self.system.frame, sent_ms=0)),
                      json.dumps(dict(self.system.frame, source='wrong'))):
            with self.subTest(frame=frame), patch.object(self.system, 'mqtt', return_value=frame):
                result = self.engine.mutate('update' if not self.engine.pending() else 'rollback', 'hhm')
                self.assertEqual(result['final_status'], 'partial_failure', result)
                self.assertEqual(result['verification_attempts'][0]['readiness']['status'], 'timeout')

    def test_slow_missing_mqtt_uses_remaining_budget_and_no_late_success(self):
        budgets = []
        def mqtt(topic, fresh=False, timeout=None):
            self.assertTrue(fresh)
            budgets.append(timeout)
            self.clock += timeout
            raise Error('No frame')
        with patch.object(self.system, 'mqtt', side_effect=mqtt):
            result = self.engine.mutate('update', 'hhm')
        self.assertEqual(result['final_status'], 'partial_failure', result)
        self.assertEqual(budgets, [30, 30])
        self.assertEqual(self.clock, 60)
        self.assertEqual(self.sleeps, [])

    def test_gazebo_waits_for_its_own_controls_and_frame(self):
        m = dict(self.hhm, role='gazebo')
        self.system.frame.update(source='ivolga-besedka-504', v=2)
        plugin = HHM()
        def control(path, timeout=None):
            self.assertTrue(path.startswith('NL_combo_thermostat_504/'))
            return 'Запуск' if self.clock < 1 else 'NORMAL'
        with patch.object(plugin, 'inventory'), patch.object(self.system, 'control', side_effect=control):
            report = plugin.verify(self.engine, m, 'original-boundary', post_restart=True)
        self.assertEqual(report['elapsed_seconds'], 1)


class ProbeBudgetTests(unittest.TestCase):
    def test_mqtt_subprocess_bounded_by_fractional_remaining_budget(self):
        system = System()
        with patch.object(system, 'run', return_value='frame') as run:
            system.mqtt('/neiro/test/frame', fresh=True, timeout=0.25)
        args, kwargs = run.call_args
        self.assertEqual(kwargs['timeout'], 0.25)
        self.assertIn('-R', args[0])
        self.assertEqual(args[0][args[0].index('-W') + 1], '1')

    def test_default_probe_unchanged_and_expired_budget_rejected(self):
        system = System()
        with patch.object(system, 'run', return_value='OK') as run:
            system.control('HHM3_FSE/runtime_status')
            self.assertEqual(run.call_args.kwargs['timeout'], 18)
            with self.assertRaises(Error):
                system.mqtt('/neiro/test/frame', timeout=0)
            self.assertEqual(run.call_count, 1)

    def test_subprocess_timeout_remains_error(self):
        with patch('nli.system.subprocess.run', side_effect=subprocess.TimeoutExpired('probe', 0.25)):
            with self.assertRaises(Error):
                System().mqtt('/neiro/test/frame', timeout=0.25)
