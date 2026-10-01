"""Approved platform assets, profile binding and clean bootstrap through real resolver."""
import copy
import json
import unittest
import test_clean_install as clean_fixtures
from test_desired_state import registry
from nst.desired import DesiredState, PlatformReleases
from nst.releases import API, RAW, Releases
from nst.util import digest


class PlatformAssetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = clean_fixtures.CleanInstallTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.deployment = f.deployment
        self.registry = registry()
        entry = self.registry['controllers']['ABCDE']
        self.profile = {k: v for k,v in entry.items() if k not in ('object', 'profile')}
        self.profile.update(schema=1, components={'demo': {'track': 'stable'}},
                            object_files=[{k:v for k,v in x.items() if k != 'sha256'} for x in self.deployment['object_files']])
        self.blobs = {RAW + self.deployment['source']['commit'] + '/' + entry['profile']: json.dumps(self.profile).encode(),
                      RAW + self.deployment['source']['commit'] + '/' + entry['diagnostics_profile']: b'{"schema":1}',
                      RAW + 'd'*40 + '/NLI/releases/demo.json': json.dumps(f.manifest).encode()}
        self.deployment['profile']['sha256'] = digest(self.blobs[RAW + self.deployment['source']['commit'] + '/' + entry['profile']])
        self.deployment['diagnostics_profile']['sha256'] = digest(b'{"schema":1}')
        self.release = dict(tag_name='nst-approved-platform-2.0', published_at='2026-10-01T00:00:00Z', draft=False, prerelease=False)
        self.releases = [self.release]
        self.refresh()
        f.engine.releases = Releases(self.fetch)
        self.desired = DesiredState(f.engine)

    def refresh(self):
        self.assets = {1: json.dumps(self.registry).encode(), 2: json.dumps(self.deployment).encode()}
        self.release['assets'] = [{'id': i, 'name': name, 'digest': 'sha256:'+digest(self.assets[i])} for i,name in
                                 ((1,'nst-controller-registry.json'),(2,'nst-deployment-ABCDE.json'))]

    def fetch(self, url, *args):
        if url.startswith(API + '/releases?'):
            return json.dumps(self.releases).encode()
        if url.startswith(API + '/releases/assets/'):
            return self.assets[int(url.rsplit('/',1)[1])]
        if url in self.blobs:
            return self.blobs[url]
        return self.fixture.fetch(url, *args)

    def test_clean_sync_uses_assets_checksums_profile_and_manifests(self):
        result = self.desired.sync()
        self.assertEqual(result['final_status'], 'ok', result)
        self.assertEqual(result['deployment_state']['status'], 'exact')

    def test_corrupted_asset_is_refused_without_writes(self):
        self.assets[1] += b'corrupt'
        self.assertEqual(self.desired.sync()['final_status'], 'failed')
        self.assertFalse(self.fixture.engine.state_dir.exists())

    def test_profile_mismatch_is_refused(self):
        self.registry['controllers']['ABCDE']['name'] = 'different'
        self.refresh()
        result = self.desired.sync()
        self.assertEqual(result['final_status'], 'failed')
        self.assertIn('Registry/profile mismatch', result['error'])

    def test_missing_latest_deployment_cannot_fall_back_to_older_approval(self):
        newer = dict(self.release, published_at='2026-10-02T00:00:00Z', assets=[])
        self.releases.append(newer)
        self.assertEqual(self.desired.sync()['final_status'], 'failed')
        self.assertFalse(self.fixture.system.actions)

    def test_draft_and_prerelease_are_not_approvals(self):
        for field in ('draft', 'prerelease'):
            self.release[field] = True
            self.assertEqual(self.desired.check()['final_status'], 'failed')
            self.release[field] = False


class PlatformPreparationTests(unittest.TestCase):
    def test_prepare_complete_assets_and_refuse_missing_capability(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        import test_deployment as fixtures
        from tools import prepare_platform_release as tool
        from nst.util import Error
        f = fixtures.DeploymentTests()
        f.setUp()
        entry = dict(f.profile, object='test_object', profile=f.profile_path)
        entry.pop('schema')
        entry.pop('components')
        entry.pop('object_files')
        registry_data = {'schema': 1, 'controllers': {'ABCDE12': entry}}
        def blob(repo, commit, path):
            if path == 'Systems/NST/generated/controller-registry.json':
                return json.dumps(registry_data).encode()
            if path == tool.APPROVALS_PATH:
                return f.approvals_raw
            return f.read(commit, path)
        with tempfile.TemporaryDirectory() as tmp, patch.object(tool, 'git_blob', side_effect=blob), patch.object(
                tool.subprocess, 'run') as ancestry, patch.object(tool, 'verify_data') as verify:
            out = Path(tmp) / 'assets'
            result = tool.build(Path(tmp), f.source, '2.0', out)
            ancestry.assert_called_once()
            verify.assert_called_once_with(f.approvals)
            self.assertEqual(set(result['assets']), {'nst-controller-registry.json', 'nst-deployment-ABCDE12.json'})
            deployment = json.loads((out / 'nst-deployment-ABCDE12.json').read_bytes())
            self.assertEqual(deployment['minimum_nst'], '2.0')
            for name, expected in result['assets'].items():
                self.assertEqual(digest((out / name).read_bytes()), expected)
            f.profile['capabilities'].append('pressure_makeup')
            f.blobs[(f.source, f.profile_path)] = json.dumps(f.profile).encode()
            with self.assertRaisesRegex(Error, 'Missing approved desired components'):
                tool.build(Path(tmp), f.source, '2.0', Path(tmp) / 'blocked')
            self.assertFalse((Path(tmp) / 'blocked').exists())
