"""Canonical WB paths, fail-closed resolution and rootfs replacement regressions."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_nli as fixtures
from nli.core import Engine
from nli.layout import CONFIG_DIR, DEFAULT_CONFIG, DATA_DIR, STATE_DIR, LOG_DIR, WB_ROOTS, load_config, target
from nli.util import Error, digest, read_json


class WBLayoutTests(fixtures.HHMTests):
    """Repeat ALL HHM cases on canonical symlinks, with no real WB backend."""
    def setUp(self):
        super().setUp()
        for alias, persistent in WB_ROOTS.items():
            real = self.root / persistent.lstrip('/')
            real.parent.mkdir(parents=True, exist_ok=True)
            link = self.root / alias.lstrip('/')
            link.rename(real)
            try:
                link.symlink_to(persistent, target_is_directory=True)
            except OSError:
                self.temp.cleanup()
                self.skipTest('Canonical symlinks require Linux or Windows symlink privilege')

    def put(self, path, data):
        p = target(self.root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_logical_backup_real_bytes_and_metadata(self):
        f = self.base['files'][0]
        p = self.engine.target(f['target'])
        self.assertIn('/mnt/data/etc/', p.as_posix())
        old_bytes = p.read_bytes()
        new_bytes = old_bytes + b'\n// updated managed bytes\n'
        self.put('/opt/payload/' + f['source'], new_bytes)
        self.new['files'][0]['sha256'] = digest(new_bytes)
        self.repin()
        p.chmod(0o640)
        original = p.stat()
        result = self.engine.mutate('update', 'hhm')
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(p.read_bytes(), new_bytes)
        meta, _ = self.engine.load_backup(result['backup'], 'hhm')
        self.assertEqual({x['target'] for x in meta['files']}, {x['target'] for x in self.base['files']})
        self.assertEqual(self.engine.mutate('rollback', 'hhm')['final_status'], 'ok')
        self.assertEqual(p.read_bytes(), old_bytes)
        self.assertEqual(p.stat().st_mode, original.st_mode)
        self.assertEqual((p.stat().st_uid, p.stat().st_gid), (original.st_uid, original.st_gid))
        for alias, persistent in WB_ROOTS.items():
            self.assertEqual(os.readlink(self.root / alias.lstrip('/')), persistent)

    def test_drift_in_persistent_rule_blocks_without_service_actions(self):
        self.put(self.base['files'][0]['target'], b'unknown writer')
        r = self.engine.mutate('update', 'hhm')
        self.assertEqual(r['final_status'], 'failed')
        self.assertIn('drift', r['error'])
        self.assertIsNone(r['backup'])
        self.assertEqual(self.system.actions, [])

    def test_retarget_root_after_engine_creation_rejected(self):
        link = self.root / 'etc/wb-rules'
        link.unlink()
        for destination in ('/tmp/evil', '../mnt/data/etc/wb-rules', '/mnt/data/etc/wb-rules/',
                            '/mnt/data/etc/other'):
            link.symlink_to(destination, target_is_directory=True)
            with self.assertRaisesRegex(Error, 'canonical WB symlink'):
                self.engine.target('/etc/wb-rules/500.js')
            link.unlink()

    def test_nested_file_and_directory_symlinks_rejected_by_inventory(self):
        folder = self.engine.target('/etc/wb-rules')
        for name, destination, is_dir in [('evil.js', '/tmp/evil', False), ('nested', '/tmp', True)]:
            link = folder / name
            link.symlink_to(destination, target_is_directory=is_dir)
            r = self.engine.read_operation('check', 'hhm')
            self.assertEqual(r['final_status'], 'failed', r)
            self.assertIn('Symlink', r['error'])
            link.unlink()

    def test_managed_symlink_rejected_before_backup(self):
        p = self.engine.target(self.base['files'][0]['target'])
        p.unlink()
        p.symlink_to('/tmp/other-rule')
        result = self.engine.mutate('update', 'hhm')
        self.assertEqual(result['final_status'], 'failed', result)
        self.assertIsNone(result['backup'])
        self.assertEqual(self.system.actions, [])

    def test_persistent_destination_chain_and_traversal_rejected(self):
        for suffix in ('/../escape', '//500.js', '/nested/../../escape'):
            with self.assertRaises(Error):
                self.engine.target('/etc/wb-rules' + suffix)
        real = self.engine.target('/etc/wb-rules')
        saved = real.with_name('saved-rules')
        real.rename(saved)
        real.symlink_to(saved, target_is_directory=True)
        with self.assertRaisesRegex(Error, 'Symlink'):
            self.engine.target('/etc/wb-rules/500.js')

    def test_missing_canonical_destination_rejected(self):
        real = self.engine.target('/etc/wb-rules')
        real.rename(real.with_name('saved-rules'))
        with self.assertRaisesRegex(Error, 'Missing canonical'):
            self.engine.target('/etc/wb-rules/500.js')


class PersistentConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.default = dict(object='unconfigured', role='unconfigured', hostname='unconfigured', components={})
        self.put(DATA_DIR + '/default-config.json', self.default)

    def put(self, path, value):
        p = target(self.root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding='utf-8')
        return p

    def test_unconfigured_readonly_creates_no_persistent_directories(self):
        e = Engine(load_config(root=self.root), self.root, fixtures.FakeSystem())
        self.assertEqual(e.read_operation('status')['final_status'], 'ok')
        self.assertEqual(e.read_operation('check', 'hhm')['final_status'], 'failed')
        self.assertFalse((self.root / 'mnt').exists())

    def test_existing_config_wins_without_overwrite(self):
        config = dict(self.default, object='preserved')
        p = self.put(DEFAULT_CONFIG, config)
        before = p.read_bytes()
        self.assertEqual(load_config(root=self.root), config)
        self.assertEqual(p.read_bytes(), before)

    def test_missing_config_never_hides_persistent_history_or_pins(self):
        for folder in (CONFIG_DIR, STATE_DIR, LOG_DIR):
            p = self.put(folder + '/retained.json', {})
            with self.assertRaisesRegex(Error, 'config is missing'):
                load_config(root=self.root)
            p.unlink()

    def test_corrupt_config_and_legacy_data_do_not_fall_back(self):
        p = self.put(DEFAULT_CONFIG, {})
        p.write_bytes(b'broken')
        with self.assertRaises(Error):
            load_config(root=self.root)
        p.unlink()
        old = self.put('/etc/neiro/nli/config.json', self.default)
        self.assertEqual(load_config(root=self.root), self.default)
        for path, value in [('/etc/neiro/nli/config.json', dict(self.default, object='old')),
                            ('/var/lib/neiro/nli/pending.json', {}), ('/var/log/neiro/nli/op.json', {})]:
            p = self.put(path, value)
            with self.assertRaisesRegex(Error, 'LEGACY_MIGRATION_REQUIRED'):
                load_config(root=self.root)
            p.unlink()

    def test_external_or_missing_explicit_config_rejected(self):
        for path in ('/etc/neiro/nli/config.json', CONFIG_DIR + '/../escape', CONFIG_DIR + '/missing.json'):
            with self.assertRaises(Error):
                load_config(path, self.root)


class RootfsRecoveryTests(fixtures.Fixture):
    def test_reinstalled_engine_reuses_pending_backup_and_audit(self):
        # Repeat core suite with persistent paths; simulate process/rootfs replacement
        # after a failed write. Neither Engine construction nor status may reset data.
        self.put(DEFAULT_CONFIG, json.dumps(self.config).encode())
        with patch.object(self.engine, 'install', side_effect=OSError('interrupted rootfs')):
            result = self.engine.mutate('update', 'demo')
        self.assertEqual(result['final_status'], 'partial_failure')
        before = self.snapshot()
        restored = Engine(load_config(root=self.root), self.root, fixtures.FakeSystem())
        status = restored.read_operation('status')
        self.assertEqual(status['final_status'], 'recovery_required')
        self.assertEqual(status['pending']['backup'], result['backup'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(restored.mutate('rollback', 'demo')['final_status'], 'ok')
        self.assertEqual(restored.current('demo')['version'], '1.0')
