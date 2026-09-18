import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publish', ROOT / 'repo/publish.py')
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class RepositoryTests(unittest.TestCase):
    def test_atomic_signed_snapshot_preserves_previous_by_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def sign(args, **kw):
                Path(args[args.index('--output') + 1]).write_text('test signature')
            with mock.patch.object(publish.subprocess, 'check_output', return_value=b'Package: old\n'), \
                 mock.patch.object(publish.subprocess, 'run', side_effect=sign):
                publish.publish(root, 'candidate', 'test-key')
            old_link = (root / 'public/dists').resolve()
            sha = publish.digest(root / 'public/dists/stonking/candidate/binary-arm64/Packages')
            with mock.patch.object(publish.subprocess, 'check_output', return_value=b'Package: new\n'), \
                 mock.patch.object(publish.subprocess, 'run', side_effect=sign):
                publish.publish(root, 'candidate', 'test-key')
            self.assertNotEqual(old_link, (root / 'public/dists').resolve())
            by_hash = root / 'public/dists/stonking/candidate/binary-arm64/by-hash/SHA256'
            self.assertEqual((by_hash / sha).read_bytes(), b'Package: old\n')
            self.assertIn('Acquire-By-Hash: yes', (root / 'public/dists/stonking/Release').read_text())
            current = (root / 'public/dists').resolve()
            with mock.patch.object(publish.subprocess, 'check_output', return_value=b'Package: bad\n'), \
                 mock.patch.object(publish.subprocess, 'run', side_effect=RuntimeError('signing failed')):
                with self.assertRaises(RuntimeError):
                    publish.publish(root, 'candidate', 'test-key')
            self.assertEqual(current, (root / 'public/dists').resolve())

    def test_legacy_payload_cannot_enter_native_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'SIGNING.json').write_text('{"signed":true}')
            with self.assertRaises(ValueError):
                publish.checked_packages(root)


if __name__ == '__main__':
    unittest.main()
