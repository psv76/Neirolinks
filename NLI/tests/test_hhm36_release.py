"""Воспроизводимость HHM 3.6 и выбор новой approved-версии NLI 0.1.9."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'NLI' / 'tools'))
sys.path.insert(0, str(ROOT / 'NLI'))
from prepare_hhm31 import prepare
from nli import __version__
from nli.plugins import HHM
from nli.releases import API, RAW, Releases, version

RUNTIME = '1faeaa094a2787ebf53dfaad19716d19076c5e2a'


class Hhm36ReleaseTests(unittest.TestCase):
    def test_version_order_is_36_newer_than_35(self):
        self.assertGreater(version('3.6'), version('3.5'))

    def test_both_roles_reproduce_runtime_and_exact_payload(self):
        for role in ('boiler', 'gazebo'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                name = 'hhm-' + role + '-3.6.json'
                raw = (ROOT / 'NLI/releases' / name).read_bytes().replace(b'\r\n', b'\n')
                manifest = json.loads(raw)
                self.assertEqual(manifest['release']['commit'], RUNTIME)
                self.assertEqual(manifest['component'], 'hhm')
                self.assertEqual(manifest['version'], '3.6')
                self.assertEqual(manifest['role'], role)
                self.assertEqual(manifest['verify']['runtime_version'], '3.6')
                self.assertEqual(manifest['verify']['health_contract'], 'm1w2-health-v1')
                self.assertEqual((ROOT / 'NLI/releases' / (name + '.sha256')).read_text().split()[0],
                                 hashlib.sha256(raw).hexdigest())
                prepare(RUNTIME, role, Path(tmp), '3.6')
                self.assertEqual((Path(tmp) / name).read_bytes(), raw)
                for entry in manifest['files']:
                    blob = subprocess.check_output(['git', 'show', RUNTIME + ':' + entry['source']], cwd=ROOT)
                    self.assertEqual(hashlib.sha256(blob).hexdigest(), entry['sha256'])
                    self.assertNotIn('507', entry['target'])

    def test_nli_019_prefers_36_over_35(self):
        self.assertEqual(__version__, '0.1.9')
        manifest_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
        documents = {}
        releases = []
        for rel_version, asset_id in (('3.5', 1), ('3.6', 2)):
            catalog = {'schema': 1, 'repository': 'psv76/Neirolinks', 'approved': True, 'components': []}
            for role in ('boiler', 'gazebo'):
                path = 'NLI/releases/hhm-' + role + '-' + rel_version + '.json'
                raw = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
                documents[RAW + manifest_commit + '/' + path] = raw
                catalog['components'].append(dict(component='hhm', object='05_31_Ivolga_13', role=role,
                    version=rel_version, approved=True, minimum_nli='0.1.9',
                    manifest=dict(commit=manifest_commit, path=path, sha256=hashlib.sha256(raw).hexdigest())))
            raw_catalog = json.dumps(catalog).encode()
            documents[API + '/releases/assets/' + str(asset_id)] = raw_catalog
            releases.append({'draft': False, 'prerelease': False, 'published_at': '2026-09-29T00:00:00Z',
                             'tag_name': 'nli-approved-hhm-' + rel_version,
                             'assets': [{'id': asset_id, 'name': 'nli-catalog.json',
                                        'digest': 'sha256:' + hashlib.sha256(raw_catalog).hexdigest()}]})
        documents[API + '/releases?per_page=100&page=1'] = json.dumps(releases).encode()
        client = Releases(lambda url, *args: documents[url])
        for role in ('boiler', 'gazebo'):
            engine = SimpleNamespace(config={'object': '05_31_Ivolga_13', 'role': role},
                                     validate=lambda m, component: HHM().validate(m, {}))
            installed = json.loads((ROOT / ('NLI/releases/hhm-' + role + '-3.5.json')).read_text())
            manifest, status = client.component(engine, 'hhm', installed)
            self.assertTrue(status['update_available'])
            self.assertEqual(manifest['version'], '3.6')
            self.assertEqual(manifest['release']['commit'], RUNTIME)


if __name__ == '__main__':
    unittest.main()
