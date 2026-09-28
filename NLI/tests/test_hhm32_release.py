"""Проверка неизменяемого NLI manifest HHM 3.2 котельной."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Hhm32ReleaseTests(unittest.TestCase):
    def test_boiler_manifest_matches_immutable_runtime(self):
        path = ROOT / 'NLI' / 'releases' / 'hhm-boiler-3.2.json'
        data = path.read_bytes()
        manifest = json.loads(data)
        self.assertEqual(manifest['version'], '3.2')
        self.assertEqual(manifest['object'], '05_31_Ivolga_13')
        self.assertEqual(manifest['role'], 'boiler')
        self.assertEqual(path.with_suffix('.json.sha256').read_text().split()[0],
                         hashlib.sha256(data).hexdigest())
        commit = manifest['release']['commit']
        self.assertEqual(commit, '4bb9cc7b26623534284c21402b61d81a9c719a33')
        for entry in manifest['files']:
            blob = subprocess.check_output(['git', 'show', commit + ':' + entry['source']], cwd=ROOT)
            head = subprocess.check_output(['git', 'show', 'HEAD:' + entry['source']], cwd=ROOT)
            self.assertEqual(hashlib.sha256(blob).hexdigest(), entry['sha256'])
            self.assertEqual(blob, head, entry['source'])
            self.assertNotIn('507', entry['target'])


if __name__ == '__main__':
    unittest.main()
