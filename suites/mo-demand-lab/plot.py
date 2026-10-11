import json,os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/workspace/mo-demand-lab/mpl-cache')
os.environ.setdefault('XDG_CACHE_HOME','/workspace/cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent;r=json.loads((root/'performance.json').read_text())['groups'];x=[g['concurrency'] for g in r];fig,axes=plt.subplots(1,2,figsize=(12,3.5),layout='constrained');axes[0].plot(x,[g['workflows_per_second'] for g in r],'o-');axes[0].set_ylabel('Business workflows / second');axes[0].set_title('MO reads + scientific decisions')
for k in ['p50','p95','p99']:axes[1].plot(x,[g['latency_ms'][k] for g in r],'o-',label=k.upper())
axes[1].set_ylabel('Complete analysis latency (ms)');axes[1].legend()
for ax in axes:ax.set_xlabel('Concurrent clients');ax.set_xticks(x);ax.grid(alpha=.2)
fig.savefig(root/'performance.png',dpi=150)
