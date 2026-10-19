import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from build_go_sdk import verified_binary


class SDKIdentity(unittest.TestCase):
    def test_exact_legacy_digest_required_without_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test-binary'; path.write_bytes(b'bounded fixture')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(verified_binary(path, expected, None, 'memos')['sha256'], expected)
            with self.assertRaises(RuntimeError):
                verified_binary(path, '0' * 64, None, 'memos')

    def test_altered_source_commit_rejected_even_when_binary_digest_matches_manifest(self):
        from build_go_sdk import ROOT
        manifest = json.loads((ROOT / 'fixtures/memos/source-manifest.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test-binary'; path.write_bytes(b'bounded fixture')
            proof = {'app': 'memos', 'passed': True, 'build_exit': 0, 'commit': '0' * 40,
                     'binary_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'source_blobs_verified': len(manifest['files']), 'go_version': 'go version go1.27.1 linux/amd64'}
            report = Path(directory) / 'manifest.json'; report.write_text(json.dumps(proof))
            with self.assertRaises(RuntimeError):
                verified_binary(path, '0' * 64, report, 'memos')

    def test_changed_adaptation_patch_digest_rejected(self):
        from build_go_sdk import ROOT
        manifest = json.loads((ROOT / 'fixtures/ntfy/source-manifest.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test-binary'; path.write_bytes(b'bounded fixture')
            proof = {'app': 'ntfy', 'passed': True, 'build_exit': 0, 'commit': manifest['commit'],
                     'binary_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'source_blobs_verified': len(manifest['files']), 'go_version': 'go version go1.27.1 linux/amd64',
                     'patch_sha256': '0' * 64}
            report = Path(directory) / 'manifest.json'; report.write_text(json.dumps(proof))
            with self.assertRaises(RuntimeError):
                verified_binary(path, '0' * 64, report, 'ntfy')

    def test_wakapi_manifest_cannot_remove_metadata_patch(self):
        from build_go_sdk import ROOT
        manifest = json.loads((ROOT / 'fixtures/wakapi/source-manifest.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test-binary'; path.write_bytes(b'bounded fixture')
            proof = {'app': 'wakapi', 'passed': True, 'build_exit': 0, 'commit': manifest['commit'],
                     'binary_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'source_blobs_verified': len(manifest['files']), 'go_version': 'go version go1.27.1 linux/amd64',
                     'patch_sha256': '0' * 64}
            report = Path(directory) / 'manifest.json'; report.write_text(json.dumps(proof))
            with self.assertRaises(RuntimeError):
                verified_binary(path, '0' * 64, report, 'wakapi')

    def test_gogs_manifest_cannot_substitute_a_different_vendor_adapter(self):
        from build_go_sdk import ROOT
        manifest = json.loads((ROOT / 'fixtures/gogs/source-manifest.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test-binary'; path.write_bytes(b'bounded fixture')
            proof = {'app': 'gogs', 'passed': True, 'build_exit': 0, 'commit': manifest['commit'],
                     'binary_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'source_blobs_verified': len(manifest['files']), 'go_version': 'go version go1.27.1 linux/amd64',
                     'adaptation_manifest_sha256': '0' * 64}
            report = Path(directory) / 'manifest.json'; report.write_text(json.dumps(proof))
            with self.assertRaises(RuntimeError):
                verified_binary(path, '0' * 64, report, 'gogs')


if __name__ == '__main__':
    unittest.main()
