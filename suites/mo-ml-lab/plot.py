"""Exportable scientific performance figure, separate from interactive HTML."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from data import ROOT
def main():
 p=json.loads((ROOT/'performance-summary.json').read_text());fig,axes=plt.subplots(1,2,figsize=(11,3.6),layout='constrained')
 for client,color in [('numpy','#1769aa'),('pandas','#098c73')]:
  rows=[r for r in p['batches'] if r['client']==client];x=[r['concurrency'] for r in rows]
  axes[0].plot(x,[r['throughput'] for r in rows],'-o',label=client,color=color);axes[1].plot(x,[r['p95_ms'] for r in rows],'-o',label=client,color=color)
 for ax in axes:ax.set_xlabel('Concurrent clients');ax.set_xticks([1,2,4,8]);ax.grid(alpha=.2);ax.legend(frameon=False)
 axes[0].set_ylabel('Verified ML workflows / second');axes[1].set_ylabel('P95 workflow latency (ms)');fig.suptitle('MO + CPU deep learning: complete training / serving workflows (4 CPU, 16 GiB)',fontsize=11)
 fig.savefig(ROOT/'performance.png',dpi=180);fig.savefig(ROOT/'performance.svg');plt.close(fig)
if __name__=='__main__':main()
