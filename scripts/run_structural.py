"""Paper threshold and ideal-cell heatmap measurement, using original seed domains."""
from pathlib import Path
import json, csv, hashlib, math
from common import ROOT,save
from build import build
from run_measurements import execute
def seed(k,l,t,role):
 return int.from_bytes(hashlib.sha256(('figure1a|114514|dense|%d|%d|%d|%s'%(k,l,t,role)).encode()).digest()[:8],'big')
def run_threshold(args,out):
 rows=[json.loads(s) for s in (ROOT/'results/reference/threshold/aggregate.jsonl').read_text().splitlines()]
 if args.limit:rows=rows[:args.limit]
 if args.dry_run:print(json.dumps({'points':len(rows),'trials_per_point':100,'field':998244353}));return
 exe=build('prime-threshold');summary=[]
 for k,l in sorted({(r['k'],r['ell']) for r in rows}):
  part=[r for r in rows if (r['k'],r['ell'])==(k,l)];n=1 if args.smoke else 100;counts=[0]*len(part)
  for t in range(n):
   roles=['dataset_identity','alice_insertion_order','bob_insertion_order','decoder_root_finding','hash_family']
   payload='figure1a-engine-v1\n%d %d %d %d %d %d %d\n'%(part[0]['set_size_A'],10000,k,l,t,len(part),args.workers)
   payload+=' '.join(str(seed(k,l,t,r)) for r in roles)+'\n'
   payload+=''.join('p%d %s %d %.17g %d\n'%(i,r['mode'],r['M'],r['a'],r['z']) for i,r in enumerate(part))
   result=execute([exe],600,payload);save(out/'records'/('%d-%d-%d.json'%(k,l,t)),result)
   if result['returncode']:raise RuntimeError(result['stderr'])
   lines=result['stdout'].splitlines();assert len(lines)==len(part)+2
   for i,line in enumerate(lines[2:]):
    v=line.split('\t');counts[i]+=int(v[2])
  for r,count in zip(part,counts):
   x={**r,'successes':count,'trials':n,'success_rate':count/n,'smoke':args.smoke};summary.append(x)
   if not args.smoke and count!=r['successes']:raise RuntimeError('Threshold success count differs from stored reference')
 save(out/'summary.json',summary);print(out)
def run_heatmaps(args,out):
 rows=list(csv.DictReader((ROOT/'results/reference/heatmaps.csv').open()));groups={}
 for r in rows:groups.setdefault((int(r['d']),int(r['M']),r['domain']),[]).append(r)
 if args.d:groups={k:v for k,v in groups.items() if k[0]==args.d}
 if args.limit:groups=dict(list(groups.items())[:args.limit])
 if args.dry_run:print(json.dumps({'panels':len(groups),'points':sum(len(v) for v in groups.values()),'trials_per_point':100}));return
 exe=build('ideal-cell');summary=[]
 for index,((d,m,domain),part) in enumerate(groups.items()):
  trials=1 if args.smoke else 100;payload='figure1bc-engine-v1\n114514\t%s\t%d\t%d\t%d\t%d\n'%(domain,d,m,trials,len(part))
  payload+=''.join('g%d\t%s\t%s\n'%(i,r['CircularBaseRange'],r['z']) for i,r in enumerate(part))
  result=execute([exe],3600,payload);save(out/'records'/(str(index)+'.json'),result)
  if result['returncode']:raise RuntimeError(result['stderr'])
  counts=[0]*len(part)
  for line in result['stdout'].splitlines():
   v=line.split('\t')
   if v[0]=='G':counts[int(v[1][1:])]+=int(v[3])
  for r,count in zip(part,counts):
   summary.append({**r,'successes':count,'trials':trials,'success_rate':count/trials,'smoke':args.smoke})
   if not args.smoke and count!=int(r['successes']):raise RuntimeError('Heatmap success count differs from stored reference')
 save(out/'summary.json',summary);print(out)
