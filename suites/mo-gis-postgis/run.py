import argparse,json
from common import P,run_cases
ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int);ap.add_argument('--workers',type=int,default=8);ap.add_argument('--results',default='results.jsonl');a=ap.parse_args()
cases=[json.loads(l) for l in (P/'cases.jsonl').read_text().splitlines()]
run_cases(cases[:a.limit] if a.limit else cases,filename=a.results,workers=a.workers)
