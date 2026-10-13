import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import superset_runtime


class SupersetSDK(unittest.TestCase):
    def fixture(self, root):
        sdk=root/'sdk';source=root/'source';fixture=root/'suite/fixtures/superset'
        (sdk/'bin').mkdir(parents=True);(sdk/'bin/python').symlink_to('/usr/bin/python3')
        site=sdk/'lib/python3.12/site-packages';site.mkdir(parents=True)
        module=site/'module.py';module.write_bytes(b'bounded original SDK source')
        (site/'core.pth').write_text(str(source/'superset-core/src')+'\n')
        original=source/'superset-core/src/core.py';original.parent.mkdir(parents=True);original.write_bytes(b'bounded original core')
        fixture.mkdir(parents=True)
        (fixture/'sdk-manifest.json').write_text(json.dumps({'version':'6.1.0','packages':[],
            'editable_core_selector':'core.pth','files':[{'path':str(module.relative_to(sdk)),
            'bytes':module.stat().st_size,'sha256':hashlib.sha256(module.read_bytes()).hexdigest()}]}))
        data=original.read_bytes();blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        (fixture/'core-source-manifest.json').write_text(json.dumps({'commit':'fixed-test-commit',
            'files':[{'path':str(original.relative_to(source)),'mode':'100644','git_blob':blob}]}))
        (fixture/'matrixone_adapter.py').write_bytes(b'bounded adapter')
        config=root/'config.json';config.write_text(json.dumps({'python_binary':str(sdk/'bin/python'),'source_tree':str(source)}))
        private=root/'private';private.mkdir()
        return sdk,module,config,private

    def test_virtualenv_executable_is_not_resolved_to_global_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sdk,module,config,private=self.fixture(root)
            with patch.object(superset_runtime,'ROOT',root/'suite'):
                python,core,identity=superset_runtime.prepare(config,private)
            self.assertEqual(python,sdk/'bin/python')
            self.assertTrue((core/'core.py').is_file())

    def test_changed_installed_dependency_is_rejected_before_native_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sdk,module,config,private=self.fixture(root);module.write_bytes(b'changed SDK')
            with patch.object(superset_runtime,'ROOT',root/'suite'):
                with self.assertRaises(RuntimeError):superset_runtime.prepare(config,private)
            self.assertFalse((private/'source').exists())
