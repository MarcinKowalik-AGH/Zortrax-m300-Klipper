"""Check that the installed and standalone release guides resolve on GitHub."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import package_release


class ExportGuideTests(unittest.TestCase):
    def test_rewrites_versioned_links_and_keeps_external_and_local_anchors(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
                package_release, 'ROOT', Path(temp)):
            root = Path(temp)
            guide = root / 'docs' / 'INSTALL.md'
            guide.parent.mkdir()
            (root / 'User Guide.md').touch()
            (root / 'images').mkdir()
            (root / 'images' / 'example.png').touch()
            guide.write_text(
                '[guide](../User%20Guide.md#setup)\n'
                '![example](../images/example.png)\n'
                '[directory](../images)\n'
                '[top](#top)\n'
                '[site](https://example.org/path)\n')
            exported = root / 'INSTALL_EN.md'
            package_release.export_guide(guide, exported)
            base = package_release.REPOSITORY
            tag = package_release.META['distribution_version']
            self.assertEqual(exported.read_text(),
                             f'[guide]({base}/blob/{tag}/User%20Guide.md#setup)\n'
                             f'![example]({base}/raw/{tag}/images/example.png)\n'
                             f'[directory]({base}/tree/{tag}/images)\n'
                             '[top](#top)\n'
                             '[site](https://example.org/path)\n')

    def test_missing_repository_target_rejects_packaging(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
                package_release, 'ROOT', Path(temp)):
            root = Path(temp)
            guide = root / 'INSTALL.md'
            guide.write_text('[missing](missing.md)\n')
            with self.assertRaisesRegex(ValueError, 'Missing guide link'):
                package_release.export_guide(guide, root / 'INSTALL_EN.md')


if __name__ == '__main__':
    unittest.main(verbosity=2)
