from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from PIL import Image
from backend.agent_bridge.image_protocol import inspect_png, ProtocolError
from local_runner.codex_image import command, native_outputs, normalize
from local_runner.images import execute_image, output_directory, select
from local_runner.opencode import LocalFailure


class ImageRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {'image_adapter': 'codex', 'image_output_dir': str(self.root / 'outputs')}
        self.request = {'id': str(uuid4()), 'attempt_id': str(uuid4()), 'schema_version': 1,
            'kind': 'image_generate', 'input': {'instructions': '生成叶片', 'references': []}}
        self.client = Mock(url='https://example.com')
        self.client.post.return_value = {'status': 'running'}

    def adapter(self, request, directory, references, **kwargs):
        result = []
        for index in range(1, 3):
            path = directory / f'candidate_{index}.png'
            Image.new('RGB', (2, 2), (index * 50, 0, 0)).save(path)
            result.append(dict(key=f'candidate_{index}', name=path.name, **inspect_png(path.read_bytes())))
        return {'candidates': result}

    @patch('local_runner.images.run')
    def test_generate_then_explicit_selection_only_uploads_chosen(self, model):
        model.side_effect = self.adapter
        execute_image(self.client, self.request, self.config)
        self.client.upload.assert_not_called()
        self.assertFalse(any('selection/' in call.args[0] for call in self.client.post.call_args_list))
        directory = output_directory(self.config, self.request['id'])
        self.assertTrue((directory / 'preview.html').exists())
        select(self.client, self.config, self.request['id'], ['candidate_2'])
        self.assertEqual(self.client.upload.call_count, 1)
        self.assertIn('/candidate_2/upload/', self.client.upload.call_args.args[0])
        self.assertEqual(model.call_count, 1)
        with self.assertRaises(ValueError):
            select(self.client, self.config, self.request['id'], ['candidate_1'])

    @patch('local_runner.images.run')
    def test_edit_fetches_only_explicit_reference_and_normalizes(self, model):
        source = self.root / 'source.jpg'
        Image.new('RGB', (2, 2)).save(source)
        self.client.reference.return_value = source.read_bytes()
        reference = str(uuid4())
        self.request['kind'] = 'image_edit'
        self.request['input']['references'] = [{'id': reference}]
        model.side_effect = self.adapter
        execute_image(self.client, self.request, self.config)
        self.assertEqual(self.client.reference.call_args.args[0], f"requests/{self.request['id']}/references/{reference}/")
        self.assertEqual(len(model.call_args.args[2]), 1)
        self.assertEqual(model.call_args.args[2][0].suffix, '.png')
        self.client.upload.assert_not_called()

    @patch('local_runner.images.time.sleep')
    @patch('local_runner.images.run')
    def test_upload_retry_keeps_same_file_and_never_generates_again(self, model, sleep):
        model.side_effect = self.adapter
        execute_image(self.client, self.request, self.config)
        self.client.upload.side_effect = [OSError(), {}]
        select(self.client, self.config, self.request['id'], ['candidate_1'])
        self.assertEqual(model.call_count, 1)
        self.assertEqual(self.client.upload.call_args_list[0], self.client.upload.call_args_list[1])

    @patch('local_runner.images.run')
    def test_tampered_file_and_symlink_rejected_before_selection(self, model):
        model.side_effect = self.adapter
        execute_image(self.client, self.request, self.config)
        directory = output_directory(self.config, self.request['id'])
        (directory / 'candidate_1.png').write_bytes(b'fake')
        self.client.reset_mock()
        with self.assertRaises(ProtocolError):
            select(self.client, self.config, self.request['id'], ['candidate_1'])
        self.client.post.assert_not_called()
        with self.assertRaises(ValueError):
            output_directory(self.config, '../../outside')
        (directory / 'candidate_2.png').unlink()
        (directory / 'candidate_2.png').symlink_to(directory / 'candidate_1.png')
        with self.assertRaises(ValueError):
            select(self.client, self.config, self.request['id'], ['candidate_2'])

    def test_native_output_scope_and_command(self):
        thread = str(uuid4())
        directory = self.root / thread
        directory.mkdir()
        (directory / 'output.png').symlink_to(self.root / 'elsewhere.png')
        with self.assertRaises(LocalFailure):
            native_outputs(self.root, thread)
        args = command('codex', self.root, [])
        self.assertIn('--ignore-user-config', args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)
        self.assertIn('shell_tool', args)

    def test_local_conversion_rejects_animation(self):
        source, target = self.root / 'animated.png', self.root / 'out.png'
        frames = [Image.new('RGB', (2, 2), color) for color in ('red', 'blue')]
        frames[0].save(source, save_all=True, append_images=frames[1:], duration=100)
        with self.assertRaises(LocalFailure):
            normalize(source, target)

    def test_conversion_removes_embedded_metadata(self):
        from PIL.PngImagePlugin import PngInfo
        source, target = self.root / 'source.png', self.root / 'clean.png'
        metadata = PngInfo()
        metadata.add_text('private', '不应回传')
        Image.new('RGB', (2, 2)).save(source, pnginfo=metadata, icc_profile=b'private-profile')
        normalize(source, target)
        with Image.open(target) as result:
            self.assertFalse(result.info)
