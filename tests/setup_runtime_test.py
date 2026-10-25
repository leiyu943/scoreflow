"""Installer failure-path tests; no network, GPU or installed packages required."""
import hashlib
import importlib.util
import io
from pathlib import Path, PurePosixPath
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('setup_runtime', Path(__file__).resolve().parents[1] / 'scripts/setup-runtime.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class InstallerTests(unittest.TestCase):
    def test_verified_cache_never_uses_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'model.pt'
            target.write_bytes(b'verified model')
            with patch.object(setup.urllib.request, 'urlopen', side_effect=AssertionError('network accessed')):
                self.assertEqual(setup.download('https://example.invalid/model', target, setup.digest(target)), target)

    def test_corrupt_cached_file_is_replaced_only_after_verification(self):
        payload = b'correct model'
        expected = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'model.pt'
            target.write_bytes(b'corrupted')
            response = io.BytesIO(payload)
            response.headers = {'Content-Length': str(len(payload))}
            with patch.object(setup.urllib.request, 'urlopen', return_value=response):
                setup.download('https://example.invalid/model', target, expected)
            self.assertEqual(target.read_bytes(), payload)

    def test_hash_failure_preserves_existing_file_and_does_not_accept_download(self):
        def response(*args, **kwargs):
            value = io.BytesIO(b'bad download')
            value.headers = {}
            return value
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'model.pt'
            target.write_bytes(b'old file')
            with patch.object(setup.urllib.request, 'urlopen', side_effect=response), patch.object(setup.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                    setup.download('https://example.invalid/model', target, '0' * 64)
            self.assertEqual(target.read_bytes(), b'old file')

    def test_zip_cannot_escape_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('source/../../escaped.txt', 'bad')
            with self.assertRaises(ValueError):
                setup.extract_selected(archive, root / 'runtime', lambda p: PurePosixPath(*p.parts[1:]))
            self.assertFalse((root / 'escaped.txt').exists())

    def test_standard_venv_and_portable_interpreters_are_both_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            standard = root / 'python/Scripts/python.exe'
            standard.parent.mkdir(parents=True)
            standard.touch()
            self.assertEqual(setup.interpreter(root), standard)
            portable = root / 'python/python.exe'
            portable.touch()
            self.assertEqual(setup.interpreter(root), portable)


if __name__ == '__main__':
    unittest.main()
