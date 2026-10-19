"""Run the published trigger without altering its SQL, worker counts or DDL."""
import json
from pathlib import Path
import runpy
import sys
import os
P=Path(__file__).resolve().parent
reproducer=Path(os.environ.get('ISSUE_REPRODUCER',str(P/'main-reproducer.py')))
namespace=runpy.run_path(str(reproducer),run_name='__main__')
Path('run-metadata.json').write_text(json.dumps({'database':namespace['DB'],
    'reproducer':str(reproducer),'writers':8,'readers':24,'ddl_operations':25,
    'changes_from_published_trigger':['local port changed to isolated test service','working/output directory isolated per run']},indent=2)+'\n')
print('RUN_DATABASE',namespace['DB'],flush=True)
