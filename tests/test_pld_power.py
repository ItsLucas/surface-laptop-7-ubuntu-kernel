"""Exercise the exact driver's protocol/freshness code without hardware access."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'drivers/qcom-pld-power'
sys.path.insert(0, str(ROOT / 'ci'))
from common import recipe_hash


class PldPowerTests(unittest.TestCase):
    def test_driver_sources_change_build_recipe(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / 'patches').mkdir()
            (root / 'patches/series').write_text('001.patch\n')
            (root / 'patches/001.patch').write_text('placeholder')
            (root / 'drivers/pld').mkdir(parents=True)
            source = root / 'drivers/pld/driver.c'
            source.write_text('version one')
            before = recipe_hash('cert', root)
            source.write_text('version two')
            self.assertNotEqual(before, recipe_hash('cert', root))

    def test_protocol_and_freshness_under_sanitizers(self):
        with tempfile.TemporaryDirectory() as work:
            for name in ('cache-test', 'protocol-test'):
                with self.subTest(name=name):
                    output = Path(work) / name
                    subprocess.run([
                        os.environ.get('CC', 'cc'), '-std=c11', '-O1', '-g',
                        '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer', '-I' + str(DRIVER / 'tests/compat'),
                        str(DRIVER / 'tests' / (name + '.c')), '-o', str(output),
                    ], check=True, timeout=30)
                    subprocess.run([output], check=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
