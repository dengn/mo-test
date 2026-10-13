"""Portable mo-test entry: fresh schemas, real native drivers, strict exit status."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from native_common import runtime_root

ROOT = Path(__file__).resolve().parent
APPS = {'gotify': 'gotify-linux-amd64', 'blocky': 'blocky', 'plik': 'plikd', 'ergo': 'ergo', 'documize': 'documize', 'huginn': None, 'ntfy': 'ntfy-matrixone', 'memos': 'memos', 'baikal': 'frankenphp', 'freshrss': 'frankenphp', 'adminer': 'frankenphp', 'phpmyadmin': 'frankenphp', 'kanboard': 'frankenphp', 'yourls': 'frankenphp', 'grafana': None, 'matomo': 'frankenphp', 'gogs': 'gogs-matrixone-fixed', 'answer': 'answer', 'opencart': 'frankenphp', 'wakapi': 'wakapi-matrixone', 'superset': None, 'strapi': None}
CONTROLS = ['PASS-GENERATED-UPPER', 'PASS-JSON-UNICODE', 'PASS-ROLLBACK']
LOAD = {'gotify': ['--messages', '128', '--workers', '4'],
        'blocky': ['--queries', '1024', '--workers', '32'],
        'plik': ['--files', '256', '--workers', '16'],
        'ergo': ['--messages', '1024', '--writers', '8', '--disable-fakelag']}


class GateBlocked(RuntimeError):
    """A deliberate refusal with a public, fixed diagnostic message."""


def plan(profile, apps=None, include_panic=False, expected_commit=None, binary_dir=None, min_free_mib=2048):
    selected = list(LOAD if profile == 'load' else APPS) if apps is None else apps
    unknown = set(selected) - set(APPS)
    if unknown:
        raise ValueError('No independent native driver: ' + ', '.join(sorted(unknown)))
    if profile not in {'smoke', 'native', 'controls', 'defects', 'observe', 'load'}:
        raise ValueError('Unknown profile')
    if apps is not None and profile in {'controls', 'defects', 'observe'}:
        raise ValueError('--app requires smoke, native or load')
    if include_panic and profile not in {'defects', 'observe'}:
        raise ValueError('--include-panic requires defects or observe on a dedicated instance')
    if expected_commit and not re.fullmatch(r'[0-9a-fA-F]{40}', expected_commit):
        raise ValueError('--expected-commit requires a full 40-character Git SHA')
    if min_free_mib < 2048 and profile == 'load':
        raise ValueError('Load profile requires at least 2048 MiB disk headroom')
    if min_free_mib < 2048 and profile in {'smoke', 'native'} and not binary_dir and any(APPS[app] for app in selected):
        raise ValueError('Below 2048 MiB native validation requires --app-binary-dir')
    if profile == 'load' and set(selected) - set(LOAD):
        raise ValueError('Load driver not yet implemented for selected app')
    jobs = []
    if profile in {'smoke', 'controls', 'defects', 'observe'}:
        args = []
        if profile in {'smoke', 'controls'}:
            for case in CONTROLS:
                args += ['--case', case]
        if profile == 'observe':
            args += ['--allow-known']
        if include_panic:
            args += ['--include-panic']
        if expected_commit:
            args += ['--expected-commit', expected_commit]
        jobs.append(('sql', 'run_sql.py', args))
    if profile in {'smoke', 'native', 'load'}:
        for app in dict.fromkeys(selected):
            args = LOAD[app].copy() if profile == 'load' else []
            if binary_dir and APPS[app]:
                args += ['--binary', str((Path(binary_dir) / APPS[app]).resolve())]
            if app in {'blocky', 'plik', 'documize', 'huginn', 'ntfy', 'memos', 'baikal', 'freshrss', 'adminer', 'phpmyadmin', 'kanboard', 'yourls', 'grafana', 'matomo', 'gogs', 'answer', 'opencart', 'wakapi', 'superset', 'strapi'}:
                args += ['--min-free-mib', str(min_free_mib)]
            jobs.append((app, 'run_' + app + '.py', args))
    return jobs


def preflight(expected_commit=None):
    import pymysql
    if 'MO_PASSWORD' not in os.environ:
        raise GateBlocked('MO_PASSWORD must be provided through the environment')
    with pymysql.connect(host=os.getenv('MO_HOST', '127.0.0.1'), port=int(os.getenv('MO_PORT', '6001')),
                         user=os.getenv('MO_USER', 'root'), password=os.environ['MO_PASSWORD'],
                         charset='utf8mb4', autocommit=True, connect_timeout=10,
                         read_timeout=15, write_timeout=15) as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT VERSION(), git_version(), 1')
            version, observed, health = cursor.fetchone()
    if 'MatrixOne' not in version or health != 1:
        raise GateBlocked('Target must be a responsive MatrixOne test instance')
    if expected_commit and not (re.fullmatch(r'[0-9a-f]{7,40}', str(observed).lower()) and
                                expected_commit.lower().startswith(str(observed).lower())):
        raise GateBlocked('Runtime commit does not match pinned source')
    return {'server_version': version, 'runtime_git_version': observed,
            'expected_commit': expected_commit, 'health': True}


def execute(jobs, out, execute_command=subprocess.run):
    """Run all selected jobs even when one fails. Never swallow failed gates."""
    records = []
    for name, script, arguments in jobs:
        started = time.monotonic()
        record = {'name': name, 'status': 'failed', 'exit_code': 2}
        try:
            result = execute_command([sys.executable, str(ROOT / script), *arguments,
                                      '--out', str(out / name)], cwd=ROOT, check=False)
            record['exit_code'] = result.returncode
            path = out / name / 'results.json'
            if path.exists():
                report = json.loads(path.read_text())
                if name == 'sql':
                    record['case_statuses'] = dict(Counter(c['status'] for c in report.get('cases', [])))
                    healthy = bool(report.get('cases')) and all(c.get('post_trigger_health') for c in report['cases'])
                    # Observe retains known_failure labels; successful observations are not passes.
                    valid = report.get('exit_code') == 0 and healthy
                    observed = bool(record['case_statuses'].get('known_failure'))
                else:
                    valid = report.get('passed') is True and bool(report.get('checks')) and all(
                        c.get('passed') is True for c in report['checks'])
                    observed = False
                    record['check_count'] = len(report.get('checks', []))
                if result.returncode == 0 and valid:
                    record['status'] = 'observed_known_failure' if observed else 'passed'
                elif result.returncode == 0:
                    record['exit_code'] = 2  # Missing/contradictory evidence must fail.
            elif result.returncode == 0:
                record['exit_code'] = 2
        except Exception as exc:
            record['error_type'] = type(exc).__name__  # Never serialize connection credentials.
        record['elapsed_seconds'] = round(time.monotonic() - started, 3)
        records.append(record)
    return records


def write_report(out, report):
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    records = report['jobs'] or [{'name': 'preflight', 'status': 'blocked', 'exit_code': 2}]
    suite = ET.Element('testsuite', name='mo-app-regression', tests=str(len(records)),
                       failures=str(sum(r['exit_code'] != 0 for r in records)))
    for record in records:
        node = ET.SubElement(suite, 'testcase', name=record['name'], classname='matrixone.app-suite',
                             time=str(record.get('elapsed_seconds', 0)))
        if record['exit_code'] != 0:
            ET.SubElement(node, 'failure', message=record['status']).text = 'See structured results.json'
        ET.SubElement(node, 'system-out').text = json.dumps(record)
    ET.ElementTree(suite).write(out / 'junit.xml', encoding='utf-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['smoke', 'native', 'controls', 'defects', 'observe', 'load'], default='smoke')
    parser.add_argument('--app', choices=list(APPS), action='append')
    parser.add_argument('--include-panic', action='store_true')
    parser.add_argument('--expected-commit')
    parser.add_argument('--app-binary-dir', type=Path, help='Optional directory of pinned official binaries')
    parser.add_argument('--min-free-mib', type=int, default=2048, help='Disk admission floor; recorded in report')
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('suite-' + uuid.uuid4().hex[:12]))
    parser.add_argument('--list', action='store_true', help='List jobs without contacting a database')
    args = parser.parse_args()
    try:
        jobs = plan(args.profile, args.app, args.include_panic, args.expected_commit, args.app_binary_dir, args.min_free_mib)
    except ValueError as exc:
        parser.error(str(exc))
    if args.min_free_mib < 128:
        parser.error('Disk admission floor must be at least 128 MiB')
    if args.list:
        print(json.dumps([{'name': name, 'script': script, 'args': opts} for name, script, opts in jobs], indent=2))
        return 0
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'profile': args.profile, 'policy': 'observation' if args.profile == 'observe' else 'strict',
              'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'jobs': [],
              'min_free_mib': args.min_free_mib, 'existing_databases_modified': False,
              'new_test_databases_preserved': True, 'runtime_logs_excluded_from_artifacts': True,
              'exit_code': 2, 'passed': False}
    try:
        report['target'] = preflight(args.expected_commit)
        report['runtime_root'] = str(runtime_root())
        report['free_bytes_at_admission'] = shutil.disk_usage(runtime_root()).free
        if report['free_bytes_at_admission'] < args.min_free_mib * 1024**2:
            raise GateBlocked('Insufficient disk headroom')
        report['workspace_free_bytes_at_admission'] = shutil.disk_usage(ROOT).free
        report['jobs'] = execute(jobs, out)
        report['exit_code'] = int(any(r['exit_code'] != 0 for r in report['jobs']))
        report['passed'] = report['exit_code'] == 0 and all(r['status'] == 'passed' for r in report['jobs'])
    except Exception as exc:
        report['blocked_error_type'] = type(exc).__name__
        if isinstance(exc, GateBlocked):
            report['blocked_reason'] = str(exc)
    report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    write_report(out, report)
    print(json.dumps({'profile': report['profile'], 'passed': report['passed'], 'exit_code': report['exit_code']}))
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
