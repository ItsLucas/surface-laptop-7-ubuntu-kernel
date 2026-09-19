import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import runpy
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from common import recipe_hash
from packaging import build_packages, embedded_dtb, ROMULUS_DTB
from pe_fixture import image_with_dtb


class PackagingTests(unittest.TestCase):
    def test_grub_dtb_alias_cleanup_keeps_payloads_and_stock_links(self):
        helper = ROOT / 'ci/package-files/support/usr/lib/sl7-kernel/grub-dtb-aliases'
        cleanup = runpy.run_path(str(helper))['remove_aliases']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); boot = root / 'boot'; boot.mkdir()
            release = '7.3.0-5-sl7.10.1'
            (boot / ('vmlinuz-' + release)).write_text('signed-efi-fixture')
            provided = root / 'usr/lib' / ('linux-image-' + release) / ROMULUS_DTB
            provided.parent.mkdir(parents=True); provided.write_bytes(b'dtb')
            for version in [release, '7.4.0-1-generic']:
                dtb = boot / 'dtbs' / version / ROMULUS_DTB
                dtb.parent.mkdir(parents=True); dtb.write_bytes(b'dtb')
                (boot / ('dtb-' + version)).symlink_to(dtb.relative_to(boot))
            # Also handle /boot/dtb recreated by a later stock-kernel install.
            (boot / 'dtb').symlink_to('dtb-7.4.0-1-generic')
            self.assertEqual(len(cleanup(root)), 2)
            self.assertFalse((boot / ('dtb-' + release)).is_symlink())
            self.assertTrue((boot / 'dtb-7.4.0-1-generic').is_file())
            self.assertEqual(provided.read_bytes(), b'dtb')
            self.assertEqual((boot / 'dtbs' / release / ROMULUS_DTB).read_bytes(), b'dtb')
            self.assertEqual(cleanup(root), [])
            # A user-created file is never removed to suppress a GRUB warning.
            (boot / 'dtb').write_text('custom-dtb')
            with self.assertRaises(RuntimeError):
                cleanup(root)
            self.assertEqual((boot / 'dtb').read_text(), 'custom-dtb')

    def test_real_package_layout_and_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            stage = out / 'package'
            (stage / 'boot').mkdir(parents=True)
            image, dtb = image_with_dtb()
            kernel = stage / 'boot/vmlinuz-7.2.0-5-sl7.4.1'
            kernel.write_bytes(image)
            with mock.patch('packaging.run') as build:
                packages = build_packages(stage, out, {'release': '7.2.0-5-sl7.4.1',
                                                      'package_version': '7.2.0-5.5+sl7.4.1'})
            self.assertEqual(len(packages), 3)
            self.assertEqual(build.call_count, 3)
            self.assertEqual((stage / 'usr/lib/linux-image-7.2.0-5-sl7.4.1' / ROMULUS_DTB).read_bytes(), dtb)
            self.assertEqual(kernel.read_bytes(), image)
            self.assertIn('dracut, linux-sl7-support', (stage / 'DEBIAN/control').read_text())
            self.assertIn('linux-image-7.2.0-5-sl7.4.1 (= 7.2.0-5.5+sl7.4.1)',
                          (out / 'meta-package/DEBIAN/control').read_text())
            for name in ['preinst', 'postinst', 'prerm', 'postrm']:
                script = stage / 'DEBIAN' / name
                self.assertTrue(os.access(script, os.X_OK))
                self.assertNotIn('@RELEASE@', script.read_text())
                subprocess.run(['sh', '-n', script], check=True)

    def test_invalid_embedded_device_tree_stops_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            image, _ = image_with_dtb()
            kernel = Path(tmp) / 'kernel.efi'
            for corrupt in [b'not a PE', image[:500], image.replace(b'\xd0\x0d\xfe\xed', b'BAD!'),
                            image.replace(b'microsoft,romulus13', b'microsoft,romulus15')]:
                kernel.write_bytes(corrupt)
                with self.assertRaises(ValueError):
                    embedded_dtb(kernel)

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
            before = recipe_hash('certificate', root)
            (root / 'tests').mkdir()
            (root / 'tests/install-smoke.py').write_text('new installation gate')
            self.assertNotEqual(before, recipe_hash('certificate', root))

    def test_follow_apt_selects_newest_complete_sl7_and_keeps_fallback(self):
        conf = ROOT / 'ci/package-files/support/etc/default/grub.d/zzzz-sl7-kernel.cfg'
        with tempfile.TemporaryDirectory() as tmp:
            boot = Path(tmp)
            releases = ['7.3.0-5-sl7.9.1', '7.3.0-5-sl7.10.1',
                        '7.4.0-1-sl7.11.1', '7.5.0-1-generic',
                        '7.3.0-5-sl7.10.1.old']
            for release in releases:
                (boot / ('vmlinuz-' + release)).write_text('kernel')
                if release != '7.4.0-1-sl7.11.1':
                    (boot / ('initrd.img-' + release)).write_text('initrd')
            def selected():
                return subprocess.check_output(['sh', '-c',
                    'SL7_FOLLOW_APT=0; . "$1"; sl7_latest_complete_kernel "$2"',
                    'test', str(conf), str(boot)], text=True).strip()
            self.assertEqual(selected(), str(boot / 'vmlinuz-7.3.0-5-sl7.10.1'))
            (boot / 'initrd.img-7.4.0-1-sl7.11.1').write_text('initrd')
            self.assertEqual(selected(), str(boot / 'vmlinuz-7.4.0-1-sl7.11.1'))
            (boot / 'vmlinuz-7.4.0-1-sl7.11.1').unlink()
            self.assertEqual(selected(), str(boot / 'vmlinuz-7.3.0-5-sl7.10.1'))


if __name__ == '__main__':
    unittest.main()
