#!/usr/bin/env python3
"""One-command entry points; --dry-run plans, --smoke runs tiny nonformal checks."""
import argparse, os, subprocess, sys
from common import ROOT,fresh
CAMPAIGNS=['paper-comparison','reference-comparison','optimized-comparison','optimized-parameters','compact-baselines','rateless','fingerprint-100000','fingerprint-1000000','optimized-sharp','extra-points','main-comparison','fingerprint']
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',choices=CAMPAIGNS+['paper-threshold','paper-heatmaps','threshold-tables','figures','verify','heuristic-calibration','rateless-representative'])
 p.add_argument('--data-root',default=os.environ.get('XYZ_DATA_ROOT',str(ROOT/'results/inputs')))
 p.add_argument('--out');p.add_argument('--d',type=int);p.add_argument('--method');p.add_argument('--kind',choices=['timing','communication'])
 p.add_argument('--limit',type=int);p.add_argument('--cpu',type=int,default=min(os.sched_getaffinity(0)));p.add_argument('--workers',type=int,default=1)
 p.add_argument('--smoke',action='store_true');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
 if a.workers<1 or a.workers>len(os.sched_getaffinity(0)):p.error('Invalid worker count')
 if a.smoke and not a.limit:a.limit=1
 if a.result=='verify':
  from verify import verify;verify();return
 if a.result=='figures':
  from plot import plot;plot(fresh('figures',a.out));return
 if a.result=='threshold-tables':
  out=fresh('threshold-tables',a.out)
  subprocess.run([sys.executable,str(ROOT/'scripts/thresholds.py'),'--appendix-grid','--format','json','--output',str(out/'thresholds.json')],check=True)
  from tables import derived;derived(out);return
 out=None if a.dry_run else fresh(a.result,a.out)
 if a.result=='rateless-representative':
  from build import build
  from common import save
  from run_measurements import execute
  import json
  if a.dry_run:print('Official-paper representative count and symbol-count checks');return
  result=execute([build('rateless'),'representative'],1800);save(out/'execution.json',result)
  if result['returncode']:raise RuntimeError(result['stderr'])
  save(out/'results.json',json.loads(result['stdout']));print(out);return
 if a.result=='heuristic-calibration':
  from calibrate import run;run(a,out);return
 if a.result=='paper-threshold':
  from run_structural import run_threshold;run_threshold(a,out)
 elif a.result=='paper-heatmaps':
  from run_structural import run_heatmaps;run_heatmaps(a,out)
 else:
  from run_measurements import run;run(a.result,a,out)
if __name__=='__main__':main()
