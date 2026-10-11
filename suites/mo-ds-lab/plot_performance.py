"""Regenerate the standalone scientific figure from reviewed benchmark samples."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def render():
    b=json.loads((ROOT/'results/supplemental/benchmark.json').read_text())['summary']
    x=[v['concurrency'] for v in b]
    fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
    axes[0].plot(x,[v.get('measured_qps',v.get('measured_qps_lower_bound')) for v in b],'o-',color='#195bb5')
    axes[0].set(ylabel='Measured query throughput (QPS)',xlabel='Concurrent clients',ylim=(0,max(v.get('measured_qps',v.get('measured_qps_lower_bound')) for v in b)*1.2),title='1,048,576 rows / three mixed queries')
    for field,label,color in [('p50_ms','P50','#195bb5'),('p95_ms','P95','#d88616'),('p99_ms','P99','#b23942')]:
        axes[1].plot(x,[v[field] for v in b],'o-',label=label,color=color)
    axes[1].set(ylabel='Client query + fetch latency (ms)',xlabel='Concurrent clients',ylim=(0,max(v['p99_ms'] for v in b)*1.1),title=f"{b[0]['measured']} measured queries per concurrency")
    axes[1].legend()
    for ax in axes:
        ax.set_xticks(x); ax.grid(alpha=.2); ax.spines[['top','right']].set_visible(False)
    fig.savefig(ROOT/'performance.png',dpi=160); fig.savefig(ROOT/'performance.svg'); plt.close(fig)

if __name__=='__main__': render()
