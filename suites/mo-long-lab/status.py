import json
from pathlib import Path
root=Path(__file__).resolve().parent
p=root/'canonical.log'
with p.open('rb') as f:f.seek(max(0,p.stat().st_size-4096));lines=f.read().decode(errors='replace').splitlines()
for line in reversed(lines):
 try:
  r=json.loads(line)
  if 'completed' in r:print(json.dumps(r));break
 except ValueError:pass
health=root/'results/canonical/health.jsonl'
rows=[json.loads(l) for l in health.read_text().splitlines()]
print(json.dumps({'heartbeats':len(rows),'errors':sum(r['status']!='ok' for r in rows),'peak_mo_rss_mib':max(r.get('rss_mib',0) for r in rows),'memory_events':Path('/sys/fs/cgroup/memory.events').read_text().splitlines()}))
