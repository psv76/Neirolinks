"""Timestamped fake journal: stale history vs observed and post-restart errors."""
from unittest.mock import patch
import unittest

import test_pressure_makeup as fixtures
from nli.system import System
from nli.util import Error

OLD = '2026-09-23T18:46:50+00:00'
START = '2026-09-24T08:00:00+00:00'
NEW = '2026-09-24T08:00:01+00:00'
ERRORS = ('SyntaxError', 'ReferenceError', 'TypeError', 'exception', 'ERROR', 'write ignored')


class VerifyWindowTests(fixtures.PressureFixture):
    def setUp(self):
        super().setUp()
        self.entries = [(OLD, 'ERROR: failed to SetValue for unexisting control')]
        self.boundaries = []
        def journal(since=None):
            self.assertIsNotNone(since, 'Never scan the whole service lifetime')
            self.boundaries.append(since)
            return '\n'.join(message for timestamp, message in self.entries if timestamp >= since)
        self.system.journal = journal

    def test_stale_errors_ignored_and_running_507_needs_no_new_marker(self):
        before = self.snapshot()
        with patch('nli.core.now', return_value=START), \
             patch.object(self.system, 'rule_started', side_effect=AssertionError('Standalone must not await restart')):
            for component in ('hhm', 'pressure_makeup'):
                result = self.engine.read_operation('verify', component)
                self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(self.boundaries, [START, START])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.system.actions, [])

    def test_errors_emitted_during_file_and_runtime_probes_fail_both_plugins(self):
        original = self.engine.files_match
        for component in ('hhm', 'pressure_makeup'):
            for message in ERRORS:
                with self.subTest(component=component, message=message):
                    self.entries = [(OLD, 'ERROR stale')]
                    def emit(m):
                        self.entries.append((NEW, message))
                        return original(m)
                    with patch('nli.core.now', return_value=START), \
                         patch.object(self.engine, 'files_match', side_effect=emit):
                        result = self.engine.read_operation('verify', component)
                    self.assertEqual(result['final_status'], 'failed', result)
                    self.assertIn('journal reports errors', result['error'])
                    self.assertEqual(self.boundaries[-1], START)
        self.assertEqual(self.system.actions, [])

    def test_new_runtime_probe_error_is_not_excluded_by_late_window_start(self):
        original = self.system.control
        def emit(path):
            self.entries.append((NEW, 'TypeError during control observation'))
            return original(path)
        with patch('nli.core.now', return_value=START), patch.object(self.system, 'control', side_effect=emit):
            for component in ('hhm', 'pressure_makeup'):
                result = self.engine.read_operation('verify', component)
                self.assertEqual(result['final_status'], 'failed', result)

    def transaction_clock(self):
        self.tick = 0
        def clock():
            self.tick += 1
            return '2026-09-24T09:00:00.{:06d}+00:00'.format(self.tick)
        return clock

    def test_every_error_after_update_restart_causes_rollback_both_plugins(self):
        clock = self.transaction_clock()
        original = self.system.service
        for component in ('hhm', 'pressure_makeup'):
            for message in ERRORS:
                with self.subTest(component=component, message=message):
                    self.entries = [(OLD, 'ERROR stale')]
                    starts = []
                    before = self.hhm_bytes(), self.engine.target(fixtures.MAKEUP_TARGET).read_bytes()
                    def emit_once(action, name):
                        original(action, name)
                        if action == 'start':
                            starts.append(clock())
                            if len(starts) == 1:
                                self.entries.append((starts[-1], message))
                    with patch('nli.core.now', side_effect=clock), patch.object(self.system, 'service', side_effect=emit_once):
                        result = self.engine.mutate('update', component)
                    self.assertEqual(result['final_status'], 'rolled_back', result)
                    self.assertEqual(len(starts), 2)
                    self.assertLess(self.boundaries[-2], starts[0])
                    self.assertGreater(self.boundaries[-1], starts[0])
                    self.assertLess(self.boundaries[-1], starts[1])
                    self.assertEqual(before, (self.hhm_bytes(), self.engine.target(fixtures.MAKEUP_TARGET).read_bytes()))
                    self.assertIsNone(self.engine.pending())

    def test_explicit_rollback_errors_preserve_pending_recovery(self):
        clock = self.transaction_clock()
        self.entries = []
        with patch('nli.core.now', side_effect=clock):
            self.assertEqual(self.engine.mutate('update', 'pressure_makeup')['final_status'], 'ok')
            original = self.system.service
            def emit(action, name):
                original(action, name)
                if action == 'start':
                    self.entries.append((clock(), 'ERROR after rollback restart'))
            with patch.object(self.system, 'service', side_effect=emit):
                result = self.engine.mutate('rollback', 'pressure_makeup')
        self.assertEqual(result['final_status'], 'partial_failure', result)
        self.assertIsNotNone(self.engine.pending())
        self.assertEqual(self.engine.read_operation('status')['final_status'], 'recovery_required')
        self.assertTrue(self.system.started[-1][1])

    def test_post_restart_marker_is_required_even_with_clean_journal(self):
        self.entries = []
        with patch.object(self.system, 'rule_started', side_effect=Error('Missing startup after restart')) as probe:
            with self.assertRaisesRegex(Error, 'Missing startup'):
                self.engine.verify(self.base, START)
        probe.assert_called_once_with('[507_Pressure_makeup] Запуск скрипта', START)


class JournalBoundaryTests(unittest.TestCase):
    def test_journal_uses_exact_boundary_without_service_activation_lookup(self):
        system = System()
        with patch.object(system, 'run', return_value='') as run:
            system.journal(START)
        run.assert_called_once_with(['/usr/bin/journalctl', '-u', 'wb-rules', '--since', START,
                                     '--no-pager', '-o', 'cat'], timeout=30)

    def test_missing_boundary_fails_closed_without_commands(self):
        system = System()
        with patch.object(system, 'run') as run:
            for since in (None, ''):
                with self.assertRaisesRegex(Error, 'observation boundary'):
                    system.journal(since)
        run.assert_not_called()
