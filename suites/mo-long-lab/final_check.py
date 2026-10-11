import json
from pathlib import Path
from data import ROOT,connect

def main():
 meta=json.loads((ROOT/'results/canonical/meta.json').read_text());c=connect();stage={}
 with c.cursor() as q:
  q.execute('SELECT VERSION()');version=q.fetchone()[0]
  for w in range(meta['workers']):
   for table in [f'stage_input_{w}',f'stage_output_{w}']:
    q.execute(f'SELECT COUNT(*) FROM {table}');n=q.fetchone()[0];stage[table]=n
    assert n==0,(table,n)
 c.close();log=Path('/workspace/mo-ds-lab/server.log')
 with log.open('rb') as f:f.seek(meta['log_start_offset']);data=f.read(meta['log_end_offset']-meta['log_start_offset'])
 (ROOT/'server-canonical.log').write_bytes(data)
 panic=[line[:1000] for line in data.decode(errors='replace').splitlines() if any(x in line for x in ['panic:','"level":"PANIC"','"level":"FATAL"'])]
 levels={};messages={}
 for line in data.decode(errors='replace').splitlines():
  try:d=json.loads(line)
  except:continue
  level=d.get('level','unknown');levels[level]=levels.get(level,0)+1
  msg=str(d.get('msg',''))[:300];messages[msg]=messages.get(msg,0)+1
 result={'stage_tables':stage,'all_stage_tables_empty':True,'server_version':version,'server_pid':Path('/workspace/mo-ds-lab/server.pid').read_text().strip(),'memory_events':Path('/sys/fs/cgroup/memory.events').read_text(),'log_levels':levels,'log_message_groups':messages,'panic_fatal':panic,'canonical_log_bytes':len(data)}
 (ROOT/'final-state.json').write_text(json.dumps(result,indent=2));print(result)
if __name__=='__main__':main()
