"""Isolated SQL regression runner; no historical result replay, no existing DB mutation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


def classify(error, expected):
    if error is None:
        return 'completed_without_error'
    code, message = error
    if expected and code == expected['code'] and all(s in message for s in expected['contains']):
        return 'known_failure'
    return 'unexpected_failure'


def main():
    import pymysql
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--include-panic', action='store_true')
    parser.add_argument('--allow-known', action='store_true', help='Observational mode only; strict CI is the default')
    parser.add_argument('--expected-commit', help='Full source SHA; refuse SQL execution when runtime git_version does not match')
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    args = parser.parse_args()
    if args.expected_commit and not re.fullmatch(r'[0-9a-fA-F]{40}', args.expected_commit):
        parser.error('--expected-commit requires a full 40-character Git SHA')
    password = os.environ.get('MO_PASSWORD')
    if password is None:
        parser.error('MO_PASSWORD must be provided through the environment')
    cases = [json.loads(p.read_text()) for p in sorted((ROOT / 'cases').glob('*.json'))]
    if args.case:
        unknown = set(args.case) - {c['id'] for c in cases}
        if unknown:
            parser.error('Unknown cases: ' + ','.join(sorted(unknown)))
        cases = [c for c in cases if c['id'] in args.case]
    if any(c.get('panic') for c in cases) and not args.include_panic:
        if args.case:
            parser.error('Selected panic cases require --include-panic on a dedicated test instance')
        cases = [c for c in cases if not c.get('panic')]
    if not cases:
        parser.error('No executable cases selected')
    args.out.mkdir(parents=True, exist_ok=False)
    report = {'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'cases': [],
              'policy': 'allow-known' if args.allow_known else 'strict', 'existing_databases_modified': False,
              'fixtures_preserved': True, 'expected_commit': args.expected_commit}
    config = dict(host=os.environ.get('MO_HOST', '127.0.0.1'), port=int(os.environ.get('MO_PORT', '6001')),
                  user=os.environ.get('MO_USER', 'root'), password=password, charset='utf8mb4',
                  autocommit=True, connect_timeout=10, read_timeout=45, write_timeout=15)
    # Credentials are never included in SQL, exception reports, or connection URLs.
    try:
        with pymysql.connect(**config) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(), git_version()')
                report['server_version'], report['runtime_git_version'] = q.fetchone()
                if 'MatrixOne' not in report['server_version']:
                    raise RuntimeError('Target is not MatrixOne')
                if args.expected_commit:
                    observed = str(report['runtime_git_version']).lower()
                    report['runtime_commit_matches'] = bool(re.fullmatch(r'[0-9a-f]{7,40}', observed) and
                                                            args.expected_commit.lower().startswith(observed))
                    if not report['runtime_commit_matches']:
                        report['connection_status'] = 'runtime_commit_mismatch'
                        raise RuntimeError('Runtime commit does not match pinned source')
    except Exception:
        report.setdefault('connection_status', 'blocked')
        (args.out / 'results.json').write_text(json.dumps(report, indent=2))
        print('Target connection/version check blocked; see results.json (credentials suppressed)')
        return 2
    for case in cases:
        started = time.monotonic()
        schema = 'mo_reg_' + uuid.uuid4().hex[:16]
        result = {'id': case['id'], 'schema': schema, 'steps': [], 'status': 'blocked',
                  'case_sha256': hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()}
        try:
            with pymysql.connect(**config) as conn:
                with conn.cursor() as q:
                    # CREATE without IF NOT EXISTS: UUID collision can never overwrite someone else's fixture.
                    q.execute('CREATE DATABASE `' + schema + '`')
                    q.execute('USE `' + schema + '`')
                    for step in case['steps']:
                        record = {'phase': step['phase'], 'sql': step['sql'], 'rows': None}
                        error = None
                        try:
                            q.execute(step['sql'])
                            record['rows'] = [list(r) for r in q.fetchall()] if q.description else []
                            record['affected_rows'] = q.rowcount
                        except pymysql.MySQLError as e:
                            # Record only errors from the public fixture SQL, never connection errors.
                            message = str(e.args[1]) if len(e.args) > 1 else type(e).__name__
                            if password and password in message:
                                message = re.sub(r'(?<!\w)' + re.escape(password) + r'(?!\w)', '<redacted>', message)
                            error = [e.args[0], message]
                            record['error'] = error
                        record['status'] = classify(error, step.get('expected_error'))
                        if error is None and 'expected_rows' in step and record['rows'] != step['expected_rows']:
                            record['status'] = 'known_failure' if record['rows'] == step.get('known_bad_rows') else 'assertion_failed'
                        result['steps'].append(record)
                        if error or record['status'] in {'assertion_failed', 'known_failure'}:
                            result['status'] = record['status'] if step['phase'] == 'trigger' else 'setup_failed'
                            break
                    else:
                        result['status'] = 'candidate_fixed' if case.get('known_issue') else 'passed'
                    # Negative tests and value audits remain mandatory even when the known failure occurs.
                    result['postchecks'] = []
                    conditional_checks = (case.get('on_success_postchecks', []) if result['status'] in {'passed', 'candidate_fixed'}
                                          else case.get('on_failure_postchecks', []) if result['status'] == 'known_failure' else [])
                    for step in case.get('postchecks', []) + conditional_checks:
                        post = {'sql': step['sql'], 'passed': False}
                        try:
                            q.execute(step['sql'])
                            post['rows'] = [list(r) for r in q.fetchall()] if q.description else []
                            post['passed'] = 'expected_rejection' not in step and post['rows'] == step.get('expected_rows', [])
                        except pymysql.MySQLError as e:
                            post['error_code'] = e.args[0]
                            post['passed'] = (e.args[0] == step.get('expected_rejection', {}).get('code') and
                                              all(s in str(e.args[1]) for s in step.get('expected_rejection', {}).get('contains', [])))
                        result['postchecks'].append(post)
                        if not post['passed']:
                            result['status'] = 'postcondition_failed'
                    # Check server responsiveness after every trigger, using a fresh SQL request.
                    try:
                        q.execute('SELECT 1')
                        result['post_trigger_health'] = q.fetchone()[0] == 1
                    except pymysql.MySQLError:
                        result['post_trigger_health'] = False
        except Exception as e:
            result['status'] = 'blocked'
            result['error_type'] = type(e).__name__
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        report['cases'].append(result)
        print(case['id'] + ': ' + result['status'])
    acceptable = {'passed', 'candidate_fixed'} | ({'known_failure'} if args.allow_known else set())
    failures = [c for c in report['cases'] if c['status'] not in acceptable or not c.get('post_trigger_health')]
    report['exit_code'] = int(bool(failures))
    report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (args.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    suite = ET.Element('testsuite', name='matrixone-sql', tests=str(len(report['cases'])), failures=str(len(failures)))
    for c in report['cases']:
        tc = ET.SubElement(suite, 'testcase', name=c['id'], classname='matrixone.sql', time=str(c['elapsed_seconds']))
        if c in failures:
            ET.SubElement(tc, 'failure', message=c['status']).text = 'See results.json for public SQL and error signature'
        ET.SubElement(tc, 'system-out').text = json.dumps({'status': c['status'], 'schema': c['schema'],
                                                        'post_trigger_health': c.get('post_trigger_health')})
    ET.ElementTree(suite).write(args.out / 'junit.xml', encoding='utf-8', xml_declaration=True)
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
