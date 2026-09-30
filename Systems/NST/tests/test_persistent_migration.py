"""Byte preservation, restartability and legacy rollback after explicit migration."""
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_core import Fixture
from nst.core import Engine
from nst.layout import CONFIG_DIR, DEFAULT_CONFIG, STATE_DIR, LOG_DIR, load_config
from nst.migration import LEGACY, CANONICAL, MARKER, migrate
from nst.util import Error, read_json, write_json


class PersistentMigrationTests(Fixture):
    def legacy(self):
        self.assertEqual(self.engine.mutate('update', self.component)['final_status'], 'ok')
        # Capture a real transaction backup and a pending rollback, not empty placeholders.
        backup = self.engine.state(self.component)['previous_backup']
        record = self.engine.record('rollback', self.component)
        record.update(backup=backup, final_status='partial_failure')
        self.engine.checkpoint(record)
        config = json.loads(json.dumps(self.config).replace(CONFIG_DIR, LEGACY[0]))
        write_json(self.engine.target(DEFAULT_CONFIG), config)
        for old, new in zip(LEGACY, CANONICAL):
            src = self.engine.target(new)
            dst = self.engine.target(old)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
        return {p: self.engine.target(p).read_bytes() for p in
                (LEGACY[0]+'/config.json', LEGACY[1]+'/pending.json',
                 LEGACY[1]+'/backups/'+backup['id']+'/metadata.json')}

    def test_preserves_originals_pending_and_rollback_references(self):
        originals = self.legacy()
        with self.assertRaisesRegex(Error, 'LEGACY_MIGRATION_REQUIRED'):
            load_config(root=self.root)
        migrate(self.root, '0.1.9')
        for path, raw in originals.items():
            self.assertEqual(self.engine.target(path).read_bytes(), raw)
        self.assertEqual(self.engine.target(STATE_DIR+'/pending.json').read_bytes(),
                         originals[LEGACY[1]+'/pending.json'])
        e = Engine(load_config(root=self.root), self.root, self.system)
        self.assertEqual(e.read_operation('status')['final_status'], 'recovery_required')
        result = e.mutate('rollback', self.component)
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(e.current(self.component)['version'], '1.0')
        before = self.snapshot()
        migrate(self.root)
        self.assertEqual(before, self.snapshot())

    def test_conflicting_canonical_data_is_never_overwritten(self):
        self.legacy()
        self.put(DEFAULT_CONFIG, b'foreign')
        with self.assertRaisesRegex(Error, 'already exists'):
            migrate(self.root, '0.1.9')
        self.assertEqual(self.engine.target(DEFAULT_CONFIG).read_bytes(), b'foreign')

    def test_interrupted_copy_resumes_without_losing_pending(self):
        original = self.legacy()
        real_replace = os.replace
        calls = []
        def interrupted(src, dst):
            if str(dst).replace('\\', '/').endswith('/var/lib/neirolinks/nst') and not calls:
                calls.append(True)
                raise OSError('simulated power loss')
            return real_replace(src, dst)
        with patch('nst.migration.os.replace', side_effect=interrupted):
            with self.assertRaises(OSError):
                migrate(self.root, '0.1.9')
        with self.assertRaisesRegex(Error, 'LEGACY_MIGRATION_REQUIRED'):
            load_config(root=self.root)
        migrate(self.root, '0.1.9')
        self.assertEqual(self.engine.target(STATE_DIR+'/pending.json').read_bytes(),
                         original[LEGACY[1]+'/pending.json'])


if __name__ == '__main__':
    unittest.main()
