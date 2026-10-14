#!/usr/bin/env python3
"""Provision one or all pinned, isolated regression environments."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--group',default='all');parser.add_argument('--python',default=sys.executable);parser.add_argument('--npm',default='npm')
    args=parser.parse_args();groups=json.loads((ROOT/'projects.json').read_text())['groups']
    selected=list(groups) if args.group=='all' else [args.group]
    if any(group not in groups for group in selected):parser.error('Unknown group')
    version=subprocess.check_output([args.python,'-c','import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")'],text=True).strip()
    if version!='3.12':parser.error('Pinned environments are validated with Python 3.12')
    env=dict(os.environ,PIP_CACHE_DIR=str(ROOT/'.cache/pip'),PIP_DISABLE_PIP_VERSION_CHECK='1',npm_config_cache=str(ROOT/'.cache/npm'))
    for group in selected:
        target=ROOT/'.venvs'/group
        subprocess.run([args.python,'-m','venv',str(target)],check=True,env=env)
        python=str(target/'bin/python')
        subprocess.run([python,'-m','pip','install','-r',str(ROOT/groups[group]['requirements'])],check=True,env=env)
        subprocess.run([python,'-m','pip','check'],check=True,env=env)
        if group=='javascript':subprocess.run([args.npm,'ci','--prefix',str(ROOT),'--no-audit','--no-fund'],check=True,env=env)
    return 0
if __name__=='__main__':raise SystemExit(main())
