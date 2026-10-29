import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import wagtail_runtime


class WagtailSDK(unittest.TestCase):
    def fixture(self, root):
        sdk = root/'sdk'; fixture = root/'suite/fixtures/wagtail'
        (sdk/'bin').mkdir(parents=True)
        (sdk/'bin/python').symlink_to('/usr/bin/python3')
        module = sdk/'lib/python3.12/site-packages/wagtail/migrations/0086_populate_grouppagepermission_permission.py'
        module.parent.mkdir(parents=True); module.write_bytes(b'bounded adapted migration')
        fixture.mkdir(parents=True); (fixture/'migration-0086-adapted.py').write_bytes(module.read_bytes())
        source = fixture/'project/settings.py'; source.parent.mkdir(); source.write_bytes(b'bounded env-only settings')
        (fixture/'sdk-manifest.json').write_text(json.dumps({
            'version': '8.0', 'source_commit': 'test-commit', 'packages': [],
            'python_sha256': hashlib.sha256((sdk/'bin/python').read_bytes()).hexdigest(),
            'official_wheel_sha256': 'test-wheel-sha', 'official_wheel_files_audited': 1,
            'modified_wheel_files': ['wagtail/migrations/0086_populate_grouppagepermission_permission.py'],
            'files': [{'path': str(module.relative_to(sdk)), 'bytes': module.stat().st_size,
                       'sha256': hashlib.sha256(module.read_bytes()).hexdigest()}]}))
        (fixture/'project-manifest.json').write_text(json.dumps({'files': [{
            'path': 'settings.py', 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]}))
        config = root/'config.json'; config.write_text(json.dumps({'python_binary': str(sdk/'bin/python')}))
        private = root/'private'; private.mkdir()
        return sdk, module, config, private

    def test_venv_identity_and_isolated_fixture_do_not_modify_prepared_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sdk, module, config, private = self.fixture(root)
            original = module.read_bytes()
            with patch.object(wagtail_runtime, 'ROOT', root/'suite'):
                python, app, identity = wagtail_runtime.prepare(config, private)
            self.assertEqual(python, sdk/'bin/python')
            self.assertEqual(module.read_bytes(), original)
            self.assertEqual((app/'settings.py').read_bytes(), b'bounded env-only settings')

    def test_altered_migration_fails_before_fixture_or_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sdk, module, config, private = self.fixture(root)
            module.write_bytes(b'altered migration')
            with patch.object(wagtail_runtime, 'ROOT', root/'suite'):
                with self.assertRaises(RuntimeError):
                    wagtail_runtime.prepare(config, private)
            self.assertFalse((private/'app').exists())
