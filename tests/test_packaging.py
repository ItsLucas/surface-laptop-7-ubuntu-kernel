import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from common import recipe_hash
from packaging import build_packages


class PackagingTests(unittest.TestCase):
    def test_real_package_layout_and_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            stage = out / 'package'
            (stage / 'boot').mkdir(parents=True)
            (stage / 'boot/vmlinuz-7.2.0-5-sl7.4.1').write_bytes(b'signed-image')
            with mock.patch('packaging.run') as build:
                packages = build_packages(stage, out, {'release': '7.2.0-5-sl7.4.1',
                                                      'package_version': '7.2.0-5.5+sl7.4.1'})
            self.assertEqual(len(packages), 3)
            self.assertEqual(build.call_count, 3)
            self.assertIn('dracut, linux-sl7-support', (stage / 'DEBIAN/control').read_text())
            self.assertIn('linux-image-7.2.0-5-sl7.4.1 (= 7.2.0-5.5+sl7.4.1)',
                          (out / 'meta-package/DEBIAN/control').read_text())
            for name in ['preinst', 'postinst', 'prerm', 'postrm']:
                script = stage / 'DEBIAN' / name
                self.assertTrue(os.access(script, os.X_OK))
                self.assertNotIn('@RELEASE@', script.read_text())
                subprocess.run(['sh', '-n', script], check=True)

    def test_dracut_config_scoped_to_sl7_and_keeps_existing_settings(self):
        conf = ROOT / 'ci/package-files/support/etc/dracut.conf.d/50-sl7.conf'
        for release in ['7.2.0-5-generic', '7.2.0-5-sl7.4.1']:
            result = subprocess.check_output(['bash', '-c',
                'kernel="$1"; add_drivers=" nvme "; install_optional_items=" /existing "; '
                'source "$2"; printf "%s|%s|%s|%s" "$add_drivers" "$install_optional_items" '
                '"${hostonly_cmdline:-unset}" "${do_strip:-unset}"', 'test', release, str(conf)], text=True)
            self.assertIn('nvme', result)
            self.assertIn('/existing', result)
            if '-sl7.' in release:
                self.assertIn('spi_hid spi_geni_qcom gpi', result)
                self.assertTrue(result.endswith('|no|no'))
            else:
                self.assertEqual(result, ' nvme | /existing |unset|unset')

    def test_migrates_only_known_legacy_boot_defaults(self):
        conf = ROOT / 'ci/package-files/support/etc/default/grub.d/zzzz-sl7-kernel.cfg'
        for value, expected in [('sl7-combined-kernel', '0'), ('sl7-spi-touchscreen-test', '0'),
                                ('saved', 'saved'), ('custom-entry', 'custom-entry'), ('2', '2')]:
            output = subprocess.check_output(['sh', '-c',
                'GRUB_DEFAULT="$1"; . "$2"; printf "%s" "$GRUB_DEFAULT"', 'test', value, str(conf)], text=True)
            self.assertEqual(output, expected)

    def test_packaging_edits_invalidate_recipe_without_python_cache_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'patches').mkdir()
            (root / 'patches/series').write_text('one.patch\n')
            (root / 'patches/one.patch').write_text('patch')
            (root / 'ci/files').mkdir(parents=True)
            hook = root / 'ci/files/postinst'
            hook.write_text('old')
            before = recipe_hash('certificate', root)
            (root / 'ci/__pycache__').mkdir()
            (root / 'ci/__pycache__/foo.pyc').write_bytes(b'cache')
            self.assertEqual(before, recipe_hash('certificate', root))
            hook.write_text('new')
            self.assertNotEqual(before, recipe_hash('certificate', root))


if __name__ == '__main__':
    unittest.main()
