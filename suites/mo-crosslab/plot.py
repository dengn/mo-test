import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parent/'mpl-cache'));os.environ.setdefault('XDG_CACHE_HOME','/workspace/cache')
import json,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent;data=json.loads((root/'performance.json').read_text())['groups']
fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
for name,label,color in [('pymysql_numpy','SQL + NumPy/SciPy','#2760ad'),('pandas_sqlalchemy','SQL + native pandas graph + science','#e18c24')]:
    rows=[r for r in data if r['client']==name];x=[r['concurrency'] for r in rows]
    axes[0].plot(x,[r['workflows_per_second'] for r in rows],'o-',label=label,color=color)
    axes[1].plot(x,[r['latency_ms']['p95'] for r in rows],'o-',label=label,color=color)
for ax in axes:ax.set_xticks([1,2,4,8]);ax.set_xlabel('Concurrent complete workflows');ax.grid(alpha=.22)
axes[0].set_ylabel('Complete workflows / second');axes[1].set_ylabel('P95 latency (ms)');axes[0].legend(fontsize=8)
fig.suptitle('19-table graph reads + scientific decisions — local 4 CPU / 16 GiB')
fig.savefig(root/'performance.png',dpi=180);fig.savefig(root/'performance.svg')
