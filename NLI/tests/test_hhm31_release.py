"""Immutable HHM 3.1 delivery; application readiness is covered separately."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'NLI' / 'tools'))
from prepare_hhm31 import prepare


class Hhm31ReleaseTests(unittest.TestCase):
    def test_both_roles_reproduce_historical_pinned_runtime(self):
        commits = set()
        for role in ('boiler', 'gazebo'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                name = 'hhm-' + role + '-3.1.json'
                path = ROOT / 'NLI' / 'releases' / name
                data = path.read_bytes()
                manifest = json.loads(data)
                commit = manifest['release']['commit']
                commits.add(commit)
                self.assertNotEqual(commit, '14354bcf1e0033c51f02f0b242bea8aa7fa29e4e')
                self.assertEqual(manifest['version'], '3.1')
                self.assertEqual(path.with_suffix('.json.sha256').read_text().split()[0],
                                 hashlib.sha256(data).hexdigest())
                prepare(commit, role, Path(tmp))
                self.assertEqual((Path(tmp) / name).read_bytes(), data)
                for entry in manifest['files']:
                    blob = subprocess.check_output(['git', 'show', commit + ':' + entry['source']], cwd=ROOT)
                    self.assertEqual(hashlib.sha256(blob).hexdigest(), entry['sha256'])
                    self.assertNotIn('507', entry['target'])
        self.assertEqual(len(commits), 1)

    def test_historical_manifests_and_recognition_are_unchanged(self):
        baseline = '4015b576b2e280569951cf7d328a83420cbd90b6'
        for folder in ('releases', 'known'):
            for role in ('boiler', 'gazebo'):
                path = 'NLI/' + folder + '/hhm-' + role + '-3.1.json'
                expected = subprocess.check_output(['git', 'show', baseline + ':' + path], cwd=ROOT)
                self.assertEqual((ROOT / path).read_bytes().replace(b'\r\n', b'\n'), expected)
                if folder == 'releases':
                    self.assertEqual((ROOT / (path + '.sha256')).read_text().split()[0],
                                     hashlib.sha256(expected).hexdigest())
