"""Approved discovery, immutable payloads and byte-only installation migration."""
import copy
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import test_nli as fixtures
from test_pressure_makeup import PressureFixture
from nli.releases import Releases, API, RAW, REPO, TransportError
from nli.layout import DATA_DIR
from nli.util import Error, digest, write_json


class DiscoveryTests(PressureFixture):
    def setUp(self):
        super().setUp()
        self.config.pop('release_source')
        self.manifest_data = json.dumps(self.new).encode()
        self.entry = dict(component=self.component, object=self.config['object'], role='boiler',
                          version='1.1', minimum_nli='0.1.8', approved=True,
                          manifest=dict(commit='a'*40, path='release.json', sha256=digest(self.manifest_data)))
        self.catalog = dict(schema=1, repository=REPO, approved=True, components=[self.entry])
        self.release = dict(id=1, tag_name='nli-approved-2026-09', published_at='2026-09-25',
                            draft=False, prerelease=False)
        self.refresh()
        self.engine.releases = Releases(self.fetch)
        self.requests = []
        self.payload_data = self.new_bytes

    def refresh(self):
        self.catalog_data = json.dumps(self.catalog).encode()
        self.release['assets'] = [dict(id=11, name='nli-catalog.json', digest='sha256:'+digest(self.catalog_data))]

    def fetch(self, url, limit=None, binary=False):
        self.requests.append(url)
        if url.startswith(API + '/releases?'):
            return json.dumps([self.release]).encode()
        if url == API + '/releases/assets/11':
            return self.catalog_data
        if url == RAW + 'a'*40 + '/release.json':
            return self.manifest_data
        if url == RAW + self.new['release']['commit'] + '/' + self.new['files'][0]['source']:
            return self.payload_data
        raise AssertionError(url)

    def test_discover_check_no_writes_update_exact_selection_then_rollback(self):
        before = self.snapshot()
        checked = self.engine.read_operation('check', self.component)
        self.assertEqual(checked['final_status'], 'ok', checked)
        self.assertEqual((checked['from_version'], checked['to_version']), ('1.0', '1.1'))
        self.assertEqual(before, self.snapshot())
        result = self.engine.mutate('update', self.component)
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(result['discovery']['manifest_sha256'], checked['discovery']['manifest_sha256'])
        self.assertEqual(self.engine.current(self.component), self.new)
        self.assertEqual(self.engine.mutate('rollback', self.component)['final_status'], 'ok')

    def test_draft_prerelease_and_wrong_role_never_selected(self):
        for field in ('draft', 'prerelease'):
            self.release[field] = True
            r = self.engine.read_operation('check', self.component)
            self.assertEqual(r['to_version'], '1.0', r)
            self.release[field] = False
        self.entry['role'] = 'gazebo'
        self.refresh()
        self.assertEqual(self.engine.read_operation('check', self.component)['to_version'], '1.0')

    def test_approved_payload_ignores_stale_legacy_bundle(self):
        self.put('/opt/payload/' + self.new['files'][0]['source'], b'stale offline bundle')
        result = self.engine.mutate('update', self.component)
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertIn(RAW + self.new['release']['commit'] + '/' + self.new['files'][0]['source'], self.requests)

    def test_package_discovery_is_metadata_only_and_requires_matching_asset(self):
        self.catalog['nli'] = dict(version='0.1.9', approved=True, sha256='a'*64)
        self.refresh()
        asset = dict(id=12, name='neiro-nli_0.1.9_all.deb', digest='sha256:'+'a'*64)
        self.release['assets'].append(asset)
        self.assertEqual(self.engine.releases.package()['version'], '0.1.9')
        self.assertNotIn(API + '/releases/assets/12', self.requests)
        asset['digest'] = 'sha256:'+'b'*64
        with self.assertRaises(Error):
            self.engine.releases.package()

    def test_invalid_approval_manifest_hash_commit_or_payload_blocks(self):
        for change in ('approval', 'hash', 'commit', 'payload'):
            with self.subTest(change=change):
                saved = copy.deepcopy(self.entry)
                if change == 'approval': self.entry['approved'] = False
                if change == 'hash': self.entry['manifest']['sha256'] = '0'*64
                if change == 'commit': self.entry['manifest']['commit'] = 'main'
                if change == 'payload': self.payload_data = b'wrong'
                self.refresh()
                r = self.engine.mutate('update', self.component)
                self.assertEqual(r['final_status'], 'failed', r)
                self.assertEqual(self.system.actions, [])
                self.entry.clear(); self.entry.update(saved)

    def test_network_error_is_unavailable_check_and_safe_update(self):
        self.engine.releases = Releases(lambda *a: (_ for _ in ()).throw(TransportError('offline')))
        before = self.snapshot()
        self.assertEqual(self.engine.read_operation('check', self.component)['final_status'], 'unavailable')
        self.assertEqual(before, self.snapshot())
        r = self.engine.mutate('update', self.component)
        self.assertEqual(r['final_status'], 'failed', r)
        self.assertEqual(self.system.actions, [])
        self.assertIsNone(r['backup'])

    def test_required_nli_has_one_command_and_no_mutation(self):
        self.entry['minimum_nli'] = '9.0.0'
        self.refresh()
        r = self.engine.read_operation('check', self.component)
        self.assertIn('nli self-update', r['error'])

    def test_no_update_has_no_restart_or_payload_fetch(self):
        self.catalog['components'] = []
        self.refresh()
        with patch.object(self.engine, 'payload', side_effect=AssertionError('No download needed')):
            r = self.engine.mutate('update', self.component)
        self.assertEqual(r['final_status'], 'ok', r)
        self.assertEqual(self.system.actions, [])


class MigrationTests(PressureFixture):
    def setUp(self):
        super().setUp()
        root = Path(__file__).resolve().parents[2]
        raw = (root / 'NLI/releases/hhm-boiler-3.1.json').read_bytes().replace(b'\r\n', b'\n')
        self.actual = json.loads(raw)
        self.put(DATA_DIR + '/known/hhm-boiler-3.1.json', raw)
        self.assertEqual(digest(raw), '3c17f811f1580306c440143de958d723d26bb3ed7151f81991d4b957d0a2eb09')
        for f in self.actual['files']:
            data = subprocess.check_output(['git', 'show', self.actual['release']['commit'] + ':' + f['source']], cwd=root)
            self.put(f['target'], data)
        write_json(self.engine.state_path('hhm'), dict(manifest=self.hhm, previous_backup=None, last_result='update_ok'))

    def test_exact_31_recognized_offline_without_files_state_or_service_changes(self):
        before = self.snapshot()
        self.system.controls['HHM3_FSE/sensor_health_contract'] = 'stale-retained-nonsense'
        with patch.object(self.engine.releases, 'component', side_effect=TransportError('offline')):
            status = self.engine.read_operation('status')
            self.assertEqual(status['components']['hhm']['manifest']['version'], '3.1', status)
            result = self.engine.read_operation('verify', 'hhm')
            self.assertEqual(result['final_status'], 'ok', result)
            self.assertEqual(result['from_version'], '3.1')
            self.config.pop('release_source')
            checked = self.engine.read_operation('check', 'hhm')
            self.assertEqual(checked['from_version'], '3.1')
            self.assertEqual(checked['final_status'], 'unavailable')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.system.actions, [])

    def test_mixed_payload_remains_unknown(self):
        self.put(self.actual['files'][0]['target'], b'// mixed old')
        status = self.engine.read_operation('status')
        self.assertEqual(status['components']['hhm']['manifest']['version'], 'unknown/drift')
        self.assertEqual(self.engine.read_operation('verify', 'hhm')['final_status'], 'failed')

    def test_first_noop_update_reconciles_without_restart(self):
        self.config.pop('release_source')
        with patch.object(self.engine.releases, 'component', return_value=(self.actual, {'update_available': False})):
            result = self.engine.mutate('update', 'hhm')
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(self.engine.state('hhm')['manifest'], self.actual)
        self.assertEqual(self.system.actions, [])


class InstallationTests(PressureFixture):
    def test_application_controls_and_frames_never_install_gates(self):
        self.system.frame = {'source': 'old', 'sent_ms': 0}
        original = self.system.control
        def safety_only(path, **kwargs):
            if path in ('pressure_makeup/active', 'A04/K1'):
                return original(path)
            raise AssertionError('Application probe forbidden: ' + path)
        with patch.object(self.system, 'control', side_effect=safety_only), \
             patch.object(self.system, 'mqtt', side_effect=AssertionError('Frame probe forbidden')):
            for component in ('hhm', 'pressure_makeup'):
                for command in ('check', 'verify'):
                    r = self.engine.read_operation(command, component)
                    self.assertEqual(r['final_status'], 'ok', r)
                self.assertEqual(self.engine.mutate('update', component)['final_status'], 'ok')
                self.assertEqual(self.engine.mutate('rollback', component)['final_status'], 'ok')

    def test_only_managed_technical_error_causes_rollback(self):
        for message, expected in [('ERROR HHM3_FSE FLOOR_SENSOR_UNAVAILABLE', 'ok'),
                                  ('SyntaxError vendor-unknown.js', 'ok'),
                                  ('SyntaxError 500_HHM3_FSE.js', 'rolled_back')]:
            with patch.object(self.system, 'journal', side_effect=[message, '']):
                r = self.engine.mutate('update', 'hhm')
            self.assertEqual(r['final_status'], expected, r)

    def test_stale_health_control_never_changes_version_after_rollback(self):
        self.system.controls['HHM3_FSE/sensor_health_contract'] = 'm1w2-health-v1'
        self.assertEqual(self.engine.mutate('update', 'hhm')['final_status'], 'ok')
        self.assertEqual(self.engine.mutate('rollback', 'hhm')['final_status'], 'ok')
        self.assertEqual(self.engine.read_operation('verify', 'hhm')['from_version'], self.hhm['version'])
