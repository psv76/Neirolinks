import copy
import io
import json
from pathlib import Path
import shutil
from unittest.mock import patch
import test_nli as fixtures
from nli import __version__
from nli.layout import STATE_DIR, LOG_DIR
from nli.self_update import SelfUpdate
from nli.retention import cleanup
from nli.util import Error, digest, write_json
from tools.build_deb import build


class MaintenanceTests(fixtures.Fixture):
    def test_success_history_bounded_and_rollback_survives(self):
        for i in range(25):
            r = self.engine.mutate('update', self.component)
            self.assertEqual(r['final_status'], 'ok', r)
        self.assertLessEqual(len(list(self.engine.log_dir.glob('*.json'))), 20)
        self.assertLessEqual(len(list(self.engine.target(STATE_DIR + '/backups').iterdir())), 3)
        self.assertEqual(self.engine.mutate('rollback', self.component)['final_status'], 'ok')

    def test_failed_evidence_and_pending_never_pruned(self):
        with patch.object(self.engine, 'verify', side_effect=Error('technical failure')):
            failed = self.engine.mutate('update', self.component)
        before = self.snapshot()
        self.assertEqual(cleanup(self.engine)['status'], 'deferred')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.engine.mutate('rollback', self.component)['final_status'], 'ok')
        for i in range(23):
            self.engine.mutate('update', self.component)
        self.assertTrue(self.engine.target(LOG_DIR + '/' + failed['id'] + '.json').exists())
        self.engine.load_backup(failed['backup'], self.component)

    def test_cleanup_failure_never_rolls_back_success(self):
        with patch('nli.retention.cleanup', side_effect=OSError('read-only storage')):
            r = self.engine.mutate('update', self.component)
        self.assertEqual(r['final_status'], 'ok', r)
        self.assertEqual(r['cleanup']['status'], 'warning')
        self.assertIsNone(self.engine.pending())
        self.assertEqual(self.engine.current(self.component)['version'], self.new['version'])

    def test_full_disk_before_services_leaves_bytes_and_pending_safe(self):
        usage = shutil._ntuple_diskusage(1, 1, 0)
        with patch('nli.core.shutil.disk_usage', return_value=usage):
            r = self.engine.mutate('update', self.component)
        self.assertEqual(r['final_status'], 'failed', r)
        self.assertIn('storage', r['error'])
        self.assertEqual(self.system.actions, [])
        self.assertIsNone(self.engine.pending())
        self.engine.files_match(self.base)

    def test_interrupt_during_cleanup_does_not_rollback_committed_update(self):
        with patch('nli.retention.cleanup', side_effect=KeyboardInterrupt):
            result = self.engine.mutate('update', self.component)
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(result['cleanup']['error'], 'KeyboardInterrupt')
        self.assertIsNone(self.engine.pending())
        self.engine.files_match(self.new)


class SelfUpdateTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        package = self.root / 'package.deb'
        with patch('sys.stdout', new=io.StringIO()):
            build(package)
        self.data = package.read_bytes()
        package.unlink()
        package.with_suffix('.deb.sha256').unlink()
        self.package = dict(version='0.1.10', approved=True, sha256=digest(self.data), asset={'id': 99})
        self.engine.releases.package = lambda: self.package
        self.engine.releases.asset = lambda *args: self.data
        self.calls = []
        def run(argv, timeout=None):
            self.calls.append(argv)
            if argv[:2] == ['/usr/bin/dpkg-deb', '-f']:
                return 'Package: neiro-nli\nVersion: 0.1.10\nArchitecture: all'
            if argv[:2] == ['/usr/bin/dpkg-query', '-W']:
                return '0.1.10'
            if argv[0] == '/usr/bin/nli':
                return '{"version": "0.1.10"}'
            self.assertEqual(argv[:2], ['/usr/bin/dpkg', '--install'])
            return ''
        self.system.run = run

    def test_check_readonly_metadata_only(self):
        before = self.snapshot()
        with patch.object(self.engine.releases, 'asset', side_effect=AssertionError('No package download')):
            r = SelfUpdate(self.engine).execute(check=True)
        self.assertTrue(r['update_available'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls, [])

    def test_no_update(self):
        self.package['version'] = __version__
        r = SelfUpdate(self.engine).execute()
        self.assertEqual(r['final_status'], 'ok')
        self.assertEqual(self.calls, [])

    def test_package_checksum_failure_before_install(self):
        self.data += b'corrupt'
        r = SelfUpdate(self.engine).execute()
        self.assertEqual(r['final_status'], 'failed', r)
        self.assertEqual(self.calls, [])

    def test_success_preserves_component_pending_and_all_durable_inputs(self):
        write_json(self.engine.pending_path, {'id': 'abc', 'component': 'demo', 'backup': None})
        before = self.snapshot()
        r = SelfUpdate(self.engine).execute()
        self.assertEqual(r['final_status'], 'ok', r)
        for name, data in before.items():
            self.assertEqual(self.snapshot()[name], data)
        self.assertEqual(self.system.actions, [])
        self.assertFalse(list(self.engine.state_dir.glob('nli-package-*')))
        self.assertFalse(self.engine.target(STATE_DIR + '/self-update.json').exists())

    def test_install_failure_retains_separate_intent_and_cleans_temp(self):
        original = self.system.run
        def fail(argv, **kwargs):
            if argv[0] == '/usr/bin/dpkg':
                raise Error('package install failed')
            return original(argv, **kwargs)
        with patch.object(self.system, 'run', side_effect=fail):
            r = SelfUpdate(self.engine).execute()
        self.assertEqual(r['final_status'], 'partial_failure', r)
        self.assertTrue(self.engine.target(STATE_DIR + '/self-update.json').exists())
        self.assertFalse(list(self.engine.state_dir.glob('nli-package-*')))
        self.assertEqual(self.engine.mutate('update', self.component)['final_status'], 'failed')
        self.assertEqual(SelfUpdate(self.engine).execute()['final_status'], 'ok')

    def test_interrupt_keeps_pending_and_never_restarts_wb(self):
        original = self.system.run
        def interrupted(argv, **kwargs):
            if argv[0] == '/usr/bin/dpkg':
                raise KeyboardInterrupt()
            return original(argv, **kwargs)
        with patch.object(self.system, 'run', side_effect=interrupted):
            result = SelfUpdate(self.engine).execute()
        self.assertEqual(result['final_status'], 'partial_failure', result)
        self.assertTrue(self.engine.target(STATE_DIR + '/self-update.json').exists())
        self.assertEqual(self.system.actions, [])

    def test_deb_rejects_foreign_data_and_hooks(self):
        from tools.build_deb import archive
        for member, entries in [('control.tar.gz', [('postinst', b'#!/bin/sh', 0o755)]),
                                ('data.tar.gz', [('mnt/data/etc/neiro/nli/config.json', b'{}', 0o644)])]:
            chunks = {'debian-binary': b'2.0\n', 'control.tar.gz': archive([('control', b'Package: neiro-nli', 0o644)],0),
                      'data.tar.gz': archive([('usr/bin/nli', b'code', 0o755)],0)}
            chunks[member] = archive(entries,0)
            data = b'!<arch>\n'
            for name, value in chunks.items():
                data += f"{name+'/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(value):<10}`\n".encode() + value
                if len(value)%2: data += b'\n'
            with self.assertRaises(Error):
                SelfUpdate.validate_deb(data)
