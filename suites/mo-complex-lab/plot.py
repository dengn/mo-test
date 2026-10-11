import json,os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/workspace/mo-complex-lab/mpl-cache')
os.environ.setdefault('XDG_CACHE_HOME','/workspace/cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
d=json.loads((root/'performance.json').read_text());rows=d['groups'];c=[r['concurrency'] for r in rows]
fig,ax=plt.subplots(1,2,figsize=(12,3.5),layout='constrained')
ax[0].plot(c,[r['queries_per_second'] for r in rows],'o-',color='#165ea6',lw=2);ax[0].set_ylabel('Complex queries / second');ax[0].set_title('Isolated mixed complex SQL throughput')
for name,color in [('p50','#008f76'),('p95','#165ea6'),('p99','#d57910')]:ax[1].plot(c,[r['latency_ms'][name] for r in rows],'o-',label=name.upper(),color=color)
ax[1].set_ylabel('Client-visible query latency (ms)');ax[1].set_title('Latency by concurrency');ax[1].legend()
for a in ax:a.set_xlabel('Concurrent clients');a.set_xticks(c);a.grid(alpha=.2);a.spines[['top','right']].set_visible(False)
fig.savefig(root/'performance.png',dpi=150)
