import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from run import execute, plan


class SuiteContract(unittest.TestCase):
    def test_smoke_has_controls_and_nineteen_real_drivers(self):
        jobs = plan('smoke')
        self.assertEqual([j[0] for j in jobs], ['sql', 'gotify', 'blocky', 'plik', 'ergo', 'documize', 'huginn', 'ntfy', 'memos', 'baikal', 'freshrss', 'adminer', 'phpmyadmin', 'kanboard', 'yourls', 'grafana', 'matomo', 'gogs', 'answer', 'opencart'])
        self.assertNotIn('--allow-known', jobs[0][2])

    def test_panic_requires_explicit_separate_profile(self):
        with self.assertRaises(ValueError):
            plan('smoke', include_panic=True)
        self.assertIn('--include-panic', plan('defects', include_panic=True)[0][2])
        self.assertNotIn('--allow-known', plan('defects')[0][2])

    def test_unmigrated_app_cannot_be_reported_as_automated(self):
        with self.assertRaises(ValueError):
            plan('native', ['gitea'])
        with self.assertRaises(ValueError):
            plan('controls', ['gotify'])

    def test_full_commit_required(self):
        with self.assertRaises(ValueError):
            plan('native', expected_commit='cd8d5ab')

    def test_low_disk_profile_cannot_admit_load_or_downloads(self):
        with self.assertRaises(ValueError):
            plan('load', binary_dir='/existing', min_free_mib=128)
        with self.assertRaises(ValueError):
            plan('smoke', min_free_mib=128)
        jobs = plan('native', ['blocky'], binary_dir='/existing', min_free_mib=128)
        self.assertIn('--min-free-mib', jobs[0][2])

    def test_runtime_sdk_driver_does_not_receive_binary_flag(self):
        job = plan('native', ['huginn'], binary_dir='/existing', min_free_mib=128)[0]
        self.assertNotIn('--binary', job[2])
        self.assertIn('--min-free-mib', job[2])

    def test_not_yet_migrated_load_is_rejected(self):
        with self.assertRaises(ValueError):
            plan('load', ['documize'])
        self.assertEqual([job[0] for job in plan('load')], ['gotify', 'blocky', 'plik', 'ergo'])

    def test_failure_does_not_hide_next_driver_or_exit_code(self):
        seen = []
        def child(command, **kwargs):
            name = Path(command[1]).stem.removeprefix('run_')
            seen.append(name)
            out = Path(command[-1]); out.mkdir()
            (out / 'results.json').write_text(json.dumps({'passed': name == 'plik',
                'checks': [{'passed': name == 'plik'}]}))
            return SimpleNamespace(returncode=1 if name == 'gotify' else 0)
        with tempfile.TemporaryDirectory() as folder:
            results = execute(plan('native', ['gotify', 'plik']), Path(folder), child)
        self.assertEqual(seen, ['gotify', 'plik'])
        self.assertEqual([r['exit_code'] for r in results], [1, 0])

    def test_zero_exit_without_actual_evidence_is_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            results = execute(plan('native', ['gotify']), Path(folder),
                              lambda *a, **kw: SimpleNamespace(returncode=0))
        self.assertEqual(results[0]['exit_code'], 2)

    def test_known_failure_observation_remains_labelled(self):
        def child(command, **kwargs):
            out = Path(command[-1]); out.mkdir()
            (out / 'results.json').write_text(json.dumps({'exit_code': 0, 'cases': [
                {'status': 'known_failure', 'post_trigger_health': True}]}))
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as folder:
            result = execute(plan('observe'), Path(folder), child)[0]
        self.assertEqual(result['status'], 'observed_known_failure')
        self.assertEqual(result['exit_code'], 0)

    def test_unhealthy_observation_fails(self):
        def child(command, **kwargs):
            out = Path(command[-1]); out.mkdir()
            (out / 'results.json').write_text(json.dumps({'exit_code': 0, 'cases': [
                {'status': 'known_failure', 'post_trigger_health': False}]}))
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as folder:
            result = execute(plan('observe'), Path(folder), child)[0]
        self.assertEqual(result['exit_code'], 2)


if __name__ == '__main__':
    unittest.main()
