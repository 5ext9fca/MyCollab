from pathlib import Path
import tempfile
import unittest

from local_runner.code_workspace import prepare, changes, git
from local_runner.opencode import LocalFailure


class CodeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-q')
        (self.source / 'rules.py').write_text('VALUE = 1\n')
        (self.source / 'delete.py').write_text('old\n')
        (self.source / 'opencode.json').write_text('{"dangerous": "ignored"}')
        (self.source / '.env').write_text('SECRET=example\n')
        git(self.source, 'add', '--all')
        git(self.source, '-c', 'user.name=Test', '-c', 'user.email=test@invalid', 'commit', '-qm', '基线')
        self.repository = {'path': self.source, 'writable_paths': ['rules.py', 'delete.py', 'new.py']}

    def test_isolated_baseline_preserves_dirty_source_and_patch_applies(self):
        original_head = git(self.source, 'rev-parse', 'HEAD')
        (self.source / 'rules.py').write_text('DIRTY = True\n')
        directory = self.root / 'work'
        commit = prepare(self.repository, directory)
        self.assertEqual(commit, original_head.decode().strip())
        self.assertEqual((directory / 'rules.py').read_text(), 'VALUE = 1\n')
        self.assertFalse((directory / '.env').exists())
        self.assertFalse((directory / 'opencode.json').exists())
        (directory / 'rules.py').write_text('VALUE = 2\n')
        (directory / 'delete.py').unlink()
        (directory / 'new.py').write_text('NEW = True\n')
        patch, files = changes(directory, self.repository['writable_paths'])
        self.assertEqual({f['change'] for f in files}, {'added', 'modified', 'deleted'})
        clean = self.root / 'clean'
        prepare(self.repository, clean)
        patch_path = self.root / 'change.patch'
        patch_path.write_bytes(patch)
        git(clean, 'apply', '--check', str(patch_path))
        git(clean, 'apply', str(patch_path))
        self.assertEqual((clean / 'rules.py').read_text(), 'VALUE = 2\n')
        self.assertEqual((self.source / 'rules.py').read_text(), 'DIRTY = True\n')
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD'), original_head)

    def test_changed_file_outside_local_permission_rejected(self):
        directory = self.root / 'work'
        prepare(self.repository, directory)
        (directory / 'outside.py').write_text('bad\n')
        with self.assertRaises(LocalFailure):
            changes(directory, ['rules.py'])

    def test_symlink_in_baseline_rejected(self):
        (self.source / 'link.py').symlink_to('/tmp/outside')
        git(self.source, 'add', '--all')
        git(self.source, '-c', 'user.name=Test', '-c', 'user.email=test@invalid', 'commit', '-qm', '链接')
        with self.assertRaises(LocalFailure):
            prepare(self.repository, self.root / 'work')

    def test_archive_attributes_cannot_silently_change_baseline(self):
        (self.source / '.gitattributes').write_text('rules.py export-ignore\n')
        git(self.source, 'add', '--all')
        git(self.source, '-c', 'user.name=Test', '-c', 'user.email=test@invalid', 'commit', '-qm', '导出属性')
        with self.assertRaises(LocalFailure):
            prepare(self.repository, self.root / 'work')

    def test_no_change_is_reported_explicitly(self):
        work = self.root / 'work'
        prepare(self.repository, work)
        with self.assertRaises(LocalFailure) as failure:
            changes(work, ['rules.py'])
        self.assertEqual(failure.exception.code, 'no_changes')
