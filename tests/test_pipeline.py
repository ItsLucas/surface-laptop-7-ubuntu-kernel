import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
from common import apply_patches, image_release, release_name, sha256, verify_files
from resolve import resolve
import notify


class VersionTests(unittest.TestCase):
    def test_next_kernel_series(self):
        self.assertEqual(image_release('linux-image-7.3.0-12-generic'), ('7.3.0', '12'))
        self.assertEqual(image_release('linux-image-7.2.0-5-generic'), ('7.2.0', '5'))
        self.assertNotEqual(release_name('7.3.0', '12', '24', '1'), release_name('7.3.0', '12', '24', '2'))

    def test_unknown_flavour_fails(self):
        with self.assertRaises(ValueError):
            image_release('linux-image-7.3.0-12-oem')

    def test_resolves_73_and_rejects_partial_publication(self):
        from types import SimpleNamespace as N
        def package(name, version, dependencies=()):
            return N(candidate=N(package=N(name=name), version=version, source_name='linux',
                                 source_version=version, uri='https://example.invalid/' + name,
                                 dependencies=dependencies))
        cache = {'linux-image-generic': package('linux-image-generic', '7.3.0-12.12',
                 [N(or_dependencies=[N(name='linux-image-7.3.0-12-generic')])])}
        for n in ['linux-image-7.3.0-12-generic', 'linux-buildinfo-7.3.0-12-generic', 'linux-source-7.3.0']:
            cache[n] = package(n, '7.3.0-12.12')
        self.assertEqual(resolve(cache)['source_package'], 'linux-source-7.3.0')
        cache['linux-source-7.3.0'].candidate.version = '7.3.0-11.11'
        with self.assertRaises(RuntimeError):
            resolve(cache)


class PatchTests(unittest.TestCase):
    def test_conflict_stops_without_silently_skipping(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'patches').mkdir(); source = root / 'source'; source.mkdir()
            (root / 'patches/series').write_text('001.patch\n')
            (root / 'patches/001.patch').write_text('--- a/value\n+++ b/value\n@@ -1 +1 @@\n-before\n+after\n')
            (source / 'value').write_text('changed-upstream\n')
            with self.assertRaises(subprocess.CalledProcessError):
                apply_patches(source, root / 'patch.log', root)
            self.assertEqual((source / 'value').read_text(), 'changed-upstream\n')


class IntegrityTests(unittest.TestCase):
    def test_tampered_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'payload').write_text('kernel')
            (root / 'FILES.json').write_text(json.dumps([{'path': 'payload', 'sha256': sha256(root / 'payload')}]))
            verify_files(root)
            (root / 'payload').write_text('tampered')
            with self.assertRaises(ValueError):
                verify_files(root)

    def test_manifest_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'FILES.json').write_text('[{"path":"../outside","sha256":"unused"}]')
            with self.assertRaises(ValueError):
                verify_files(root)


class NotificationTests(unittest.TestCase):
    @mock.patch.dict('os.environ', {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_REPOSITORY_OWNER': 'owner',
                                  'GITHUB_RUN_ID': '123', 'GITHUB_SHA': 'abc', 'BUILD_RESULT': 'skipped'})
    def test_failure_mentions_owner_and_run(self):
        with mock.patch.object(notify, 'api', side_effect=[[], {'number': 1}]) as api:
            notify.main()
            payload = api.call_args.args[2]
            self.assertIn('@owner', payload['body'])
            self.assertIn('/actions/runs/123', payload['body'])
            self.assertEqual(api.call_args.args[0:2], ('/issues', 'POST'))


if __name__ == '__main__':
    unittest.main()
