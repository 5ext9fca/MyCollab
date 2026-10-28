"""发行归档的纯文件测试，不构建或执行安装程序。"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from collect_release import collect


class ReleaseCollectionTests(unittest.TestCase):
    def test_collect_only_distribution_files_with_hashes(self):
        for target, names in [
            ('mac-arm64', ['MyCollab.dmg', 'MyCollab.zip', 'latest-mac.yml']),
            ('mac-x64', ['MyCollab.dmg', 'MyCollab.zip', 'latest-mac.yml']),
            ('win-x64', ['MyCollab.exe', 'latest.yml']),
        ]:
            with self.subTest(target=target), TemporaryDirectory() as folder:
                source = Path(folder) / 'source'
                source.mkdir()
                output = Path(folder) / 'output'
                for name in [*names, 'MyCollab.blockmap', 'builder-debug.yml', 'certificate.p12']:
                    (source / name).write_bytes(name.encode())
                collect(source, output, target, 'revision')
                expected = {*names, 'MyCollab.blockmap', 'SHA256SUMS.txt', 'build-info.json'}
                self.assertEqual({p.name for p in output.iterdir()}, expected)
                self.assertEqual(json.loads((output / 'build-info.json').read_text()),
                                 {'target': target, 'revision': 'revision'})
                for line in (output / 'SHA256SUMS.txt').read_text().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(digest, hashlib.sha256((output / name).read_bytes()).hexdigest())

    def test_missing_manifest_or_duplicate_installers_fail_before_copy(self):
        for names in [['MyCollab.exe'], ['latest.yml'], ['one.exe', 'two.exe', 'latest.yml']]:
            with self.subTest(names=names), TemporaryDirectory() as folder:
                source = Path(folder) / 'source'
                source.mkdir()
                output = Path(folder) / 'output'
                for name in names:
                    (source / name).touch()
                with self.assertRaises(ValueError):
                    collect(source, output, 'win-x64', 'revision')
                self.assertFalse(output.exists())

    def test_existing_output_is_not_overwritten(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            source.mkdir()
            (source / 'MyCollab.exe').touch()
            (source / 'latest.yml').touch()
            output = Path(folder) / 'output'
            output.mkdir()
            previous = output / 'previous'
            previous.write_text('保留')
            with self.assertRaises(ValueError):
                collect(source, output, 'win-x64', 'revision')
            self.assertEqual(previous.read_text(), '保留')
            self.assertEqual(list(output.iterdir()), [previous])


if __name__ == '__main__':
    unittest.main()
