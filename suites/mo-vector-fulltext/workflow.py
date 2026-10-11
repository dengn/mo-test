import os,sys,subprocess
from pathlib import Path
p=Path('/workspace/mo-vector-fulltext');env=os.environ.copy();env['OPENBLAS_NUM_THREADS']='1'
def run(script,*args):
    tag=script.removesuffix('.py')+('-'+'-'.join(args) if args else '')
    with open(p/(tag+'.log'),'w') as f:
        r=subprocess.run([sys.executable,str(p/script),*args],stdout=f,stderr=subprocess.STDOUT,env=env)
    print(tag,r.returncode,flush=True)
    if r.returncode:raise SystemExit(r.returncode)
if sys.argv[1]=='first':
    run('fulltext_controls.py');run('query_boundaries.py');run('semantic_edges.py');run('quantization.py');run('mutation.py','run','index_write_normal','90','0');run('mutation.py','audit','before_crash')
elif sys.argv[1]=='resume_first':
    run('semantic_edges.py');run('quantization.py');run('mutation.py','run','index_write_normal','90','0');run('mutation.py','audit','before_crash')
elif sys.argv[1]=='finish':
    run('mutation.py','audit','after_crash');run('mutation.py','maintenance');run('concurrent_reindex.py');run('mutation.py','audit','after_concurrent_reindex');run('vector_posting_audit.py');run('suite.py','oracle','after_recovery');run('tune.py')
elif sys.argv[1]=='last':
    run('freshness_control.py');run('duplicate_tune.py');run('vector_posting_audit.py');run('mutation.py','audit','final')
