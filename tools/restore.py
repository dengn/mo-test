#!/usr/bin/env python3
"""Verify and restore every byte of the frozen test bundles; stdlib only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def restore(suite, destination, verify_only=False):
    with tempfile.TemporaryFile() as archive:
        whole = hashlib.sha256()
        size = 0
        for part in suite['parts']:
            data = (ROOT / part['path']).read_bytes()
            assert len(data) == part['bytes'], part['path']
            assert hashlib.sha256(data).hexdigest() == part['sha256'], part['path']
            archive.write(data)
            whole.update(data)
            size += len(data)
        assert size == suite['archive_bytes'], suite['name']
        assert whole.hexdigest() == suite['archive_sha256'], suite['name']
        archive.seek(0)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None, suite['name']
            if not verify_only:
                target = (destination / suite['name']).resolve()
                assert not target.exists(), f'Refusing to overwrite {target}'
                target.mkdir(parents=True)
                for member in z.infolist():
                    name = member.filename
                    if suite['zip_prefix']:
                        assert name.startswith(suite['zip_prefix']), name
                        name = name[len(suite['zip_prefix']):]
                    if not name:
                        continue
                    output = (target / name).resolve()
                    assert output.is_relative_to(target), name
                    if member.is_dir():
                        output.mkdir(parents=True, exist_ok=True)
                    else:
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as source, output.open('wb') as sink:
                            while block := source.read(1024 * 1024):
                                sink.write(block)
                        mode = member.external_attr >> 16
                        if mode:
                            os.chmod(output, mode & 0o777)
        print(f"{suite['name']}: SHA256 + ZIP CRC verified" + ('' if verify_only else f'; restored to {target}'), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', action='append', help='Lab name; repeatable; default all suites')
    parser.add_argument('--output', type=Path, default=ROOT / 'work')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'archives/manifest.json').read_text())
    names = {suite['name'] for suite in manifest['suites']}
    assert not set(args.suite or []).difference(names), 'Unknown suite'
    for suite in manifest['suites']:
        if not args.suite or suite['name'] in args.suite:
            restore(suite, args.output, args.verify_only)

if __name__ == '__main__':
    main()
