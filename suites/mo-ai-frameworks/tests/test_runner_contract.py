"""The regression gate must reject incomplete/failed evidence even after exit 0."""
import unittest,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run import evaluate_junit

class GateContract(unittest.TestCase):
    def test_missing_skip_failure_are_not_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'junit.xml'
            path.write_text('<testsuites><testsuite><testcase name="ok"/><testcase name="skipped"><skipped/></testcase><testcase name="broken"><failure/></testcase></testsuite></testsuites>')
            result=evaluate_junit(path,['ok','skipped','broken','not-collected'])
            self.assertEqual(result['passed'],['ok'])
            self.assertEqual(set(result['missing']),{'skipped','broken','not-collected'})
            self.assertEqual({r['status'] for r in result['problems']},{'skipped','failure'})
    def test_absent_and_invalid_xml_are_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'junit.xml'
            self.assertEqual(evaluate_junit(path,['required'])['missing'],['required'])
            path.write_text('incomplete XML')
            self.assertTrue(evaluate_junit(path,['required'])['problems'])
if __name__=='__main__':unittest.main()
