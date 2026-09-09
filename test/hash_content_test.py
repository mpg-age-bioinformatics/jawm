"""Canonical dataset hash regression tests: python test/hash_content_test.py."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from jawm.utils import hash_content, write_hash_file


class HashContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jawm_hash_content_')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'
        self.data.mkdir()

    def put(self, name, data):
        path = self.data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_known_versioned_encoding(self):
        self.put('a.txt', b'ABC')
        payload = b'["jawm-file-manifest-v2",true,[["a.txt",3,"b5d4045c3f466fa91fe2cc6abe79232a1a57cdf104f7a26e716e0a1e2789df78"]]]'
        self.assertEqual(hash_content(self.data), hashlib.sha256(payload).hexdigest())
        self.assertNotEqual(hash_content(self.data), hashlib.sha256(b'ABC').hexdigest())

    def test_changed_file_boundaries_fail_in_both_modes(self):
        for names in (True, False):
            self.put('a', b'AB'); self.put('b', b'C')
            baseline = hash_content(self.data, consider_name=names)
            self.put('a', b'A'); self.put('b', b'BC')
            self.assertNotEqual(baseline, hash_content(self.data, consider_name=names))

    def test_empty_file_addition_and_removal_change_hash(self):
        self.put('a', b'ABC')
        original = hash_content(self.data)
        empty = self.put('empty', b'')
        self.assertNotEqual(original, hash_content(self.data))
        empty.unlink()
        self.assertEqual(original, hash_content(self.data))
        self.assertNotEqual(hash_content([]), hash_content(self.put('empty', b'')))

    def test_relative_paths_distinguish_moves_with_same_basename(self):
        source = self.put('left/file', b'ABC')
        original = hash_content(self.data)
        content = hash_content(self.data, consider_name=False)
        (self.data / 'right').mkdir()
        source.rename(self.data / 'right/file')
        self.assertNotEqual(original, hash_content(self.data))
        self.assertEqual(content, hash_content(self.data, consider_name=False))

    def test_names_are_unambiguously_framed(self):
        a = self.put('A', b'BC')
        old = hash_content(self.data)
        a.unlink(); self.put('AB', b'C')
        self.assertNotEqual(old, hash_content(self.data))

    def test_relocation_order_and_overlapping_selections(self):
        a = self.put('a', b'A'); b = self.put('nested/b', b'B')
        baseline = hash_content(self.data)
        self.assertEqual(baseline, hash_content([b, a]))
        self.assertEqual(baseline, hash_content([a, b, self.data, a]))
        copy = self.root / 'copy'
        shutil.copytree(self.data, copy)
        self.assertEqual(baseline, hash_content(copy))

    def test_identical_content_in_distinct_files_is_counted(self):
        a = self.put('a', b'A'); b = self.put('b', b'A')
        self.assertNotEqual(hash_content(a, consider_name=False),
                            hash_content([a, b], consider_name=False))

    def test_filters_and_nonrecursive_mode(self):
        a = self.put('a.txt', b'A')
        self.put('b.bin', b'B'); self.put('nested/c.txt', b'C')
        self.assertEqual(hash_content(a), hash_content(self.data, allowed_extensions=['txt'], recursive=False))
        baseline = hash_content(self.data, exclude_dirs=['nested'], exclude_files=['*.bin'])
        self.assertEqual(hash_content(a), baseline)
        self.put('b.bin', b'CHANGED')
        self.assertEqual(baseline, hash_content(self.data, exclude_dirs=['nested'], exclude_files=['*.bin']))

    def test_missing_input_fails_instead_of_silent_omission(self):
        a = self.put('a', b'A')
        with self.assertRaises(FileNotFoundError):
            hash_content([a, self.data / 'missing'])

    def test_symlinks_and_nonregular_files_are_rejected(self):
        self.put('a', b'A')
        link = self.data / 'link'
        link.symlink_to('a')
        with self.assertRaises(ValueError): hash_content(self.data)
        link.unlink(); link.symlink_to('absent')
        with self.assertRaises(ValueError): hash_content(self.data)
        link.unlink(); link.symlink_to('.', target_is_directory=True)
        with self.assertRaises(ValueError): hash_content(self.data)
        link.unlink(); os.mkfifo(link)
        with self.assertRaises(ValueError): hash_content(self.data)

    def test_unreadable_file_and_directory_fail(self):
        self.put('a', b'A')
        with patch('builtins.open', side_effect=PermissionError('unreadable')):
            with self.assertRaises(PermissionError): hash_content(self.data)
        with patch('os.scandir', side_effect=PermissionError('unreadable directory')):
            with self.assertRaises(PermissionError): hash_content(self.data)

    def test_write_hash_file_forwards_explicit_content_only_option(self):
        a = self.put('a', b'A')
        target = self.root / 'expected.hash'
        self.assertTrue(write_hash_file(a, target, consider_name=False, v=False))
        a.rename(self.data / 'b')
        self.assertTrue(write_hash_file(self.data / 'b', target, consider_name=False, v=False))
        self.assertFalse(write_hash_file(self.data / 'b', target, v=False))

    def test_cli_reference_rejects_former_boundary_collision(self):
        self.put('a', b'AB'); self.put('b', b'C')
        reference = hash_content(self.data)
        self.put('a', b'A'); self.put('b', b'BC')
        (self.root / 'workflow.py').write_text('import sys\nsys.exit(0)\n')
        (self.root / 'params.yaml').write_text('- scope: hash\n  include: [data]\n  reference: ' + reference + '\n')
        env = {k: v for k, v in os.environ.items() if not k.startswith('JAWM_')}
        env.update(PYTHONPATH=str(REPO), JAWM_CONFIG_FILE='/dev/null',
                   JAWM_MONITORING_DIRECTORY=str(self.root / 'monitoring'))
        result = subprocess.run([sys.executable, '-m', 'jawm.cli', 'workflow.py', '-p', 'params.yaml'],
                                cwd=self.root, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 73, result.stdout + result.stderr)
        manifest = json.loads(next((self.root / 'logs/jawm_hashes').glob('*manifest.json')).read_text())
        self.assertEqual(manifest['aggregate_format'], 'jawm-file-manifest-v2')


if __name__ == '__main__':
    unittest.main(verbosity=2)
