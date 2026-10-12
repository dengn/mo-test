import unittest
from run_sql import classify


class Classification(unittest.TestCase):
    def setUp(self):
        self.expected = {'code': 20101, 'contains': ['panic', 'strCaseFn', 'unsafe slice cast']}

    def test_complete_signature(self):
        self.assertEqual(classify([20101, 'panic unsafe slice cast in strCaseFn'], self.expected), 'known_failure')

    def test_same_code_other_failure_does_not_match(self):
        self.assertEqual(classify([20101, 'table does not exist'], self.expected), 'unexpected_failure')

    def test_missing_stack_frame_does_not_match(self):
        self.assertEqual(classify([20101, 'panic unsafe slice cast in otherFunction'], self.expected), 'unexpected_failure')

    def test_changed_code_does_not_match(self):
        self.assertEqual(classify([1064, 'panic unsafe slice cast in strCaseFn'], self.expected), 'unexpected_failure')

    def test_no_error_is_distinct_from_known_failure(self):
        self.assertEqual(classify(None, self.expected), 'completed_without_error')


if __name__ == '__main__':
    unittest.main()
