"""Recompute the final heuristic fit on its recorded finite grid, deduplicating geometry."""
import json,gzip,csv,math,sys
from common import ROOT,load,save
from build import build
from run_measurements import execute
def run(args,out):
 with gzip.open(ROOT/'results/calibration/relative_scores.csv.gz','rt') as f:candidates=[r for r in csv.DictReader(f) if r['stage']=='fine_final']
 points=load(ROOT/'results/calibration/fine-points.json')
 if args.limit:points=points[:args.limit]
 if args.dry_run:
  print(json.dumps({'points':len(points),'candidates':len(candidates),'trials':100,'geometry_deduplication':True}));return
 sys.path.insert(0,str(ROOT/'scripts/protocols'))
 from figure1bc.relative import relative_score_point_rows
 frozen=load(ROOT/'results/calibration/frozen_parameters.json');ratio=frozen['c_peel']/frozen['c_orient'];exe=build('ideal-cell');cfg=load(ROOT/'results/calibration/calibration_config.json')
 def measured():
  for index,point in enumerate(points):
   d,m=point['d'],point['M'];groups={};maps=[]
   for r in candidates:
    a=float(r['C'])*ratio;gamma=float(r['gamma']);z=math.floor(gamma*(1-a)**(2/3)*m**(1/3)+.5)
    if not 0<a<1 or not 1<=z<m:maps.append(None);continue
    span=m//(z+1);cdr=min(m,m-span+1+math.floor(a*span));key=(cdr,z)
    if key not in groups:groups[key]=len(groups)
    maps.append(groups[key])
   trials=1 if args.smoke else 100
   payload='figure1bc-engine-v1\n114514\tcalibration_fine\t%d\t%d\t%d\t%d\n'%(d,m,trials,len(groups))
   payload+=''.join('g%d\t%d\t%d\n'%(i,cdr,z) for (cdr,z),i in groups.items())
   r=execute([exe],3600,payload);save(out/'records'/('%06d.json'%index),{'point':point,'execution':r,'smoke':args.smoke})
   if r['returncode']:raise RuntimeError(r['stderr'])
   counts=[0]*len(groups)
   for line in r['stdout'].splitlines():
    fields=line.split('\t')
    if fields[0]=='G':counts[int(fields[1][1:])]+=int(fields[3])
   yield [{'d':d,'M':m,'candidate_id':c['candidate_id'],'C':float(c['C']),'gamma':float(c['gamma']),'trials':trials,'successes':0 if g is None else counts[g]} for c,g in zip(candidates,maps)]
 if args.smoke or args.limit:
  sizes=[len(x) for x in measured()];save(out/'partial.json',{'points':len(sizes),'candidates_per_point':sizes,'formal_fit':False});print(out);return
 best,scores=relative_score_point_rows(measured(),cfg['training_d']);save(out/'selected.json',best.to_dict());save(out/'scores.json',scores)
 assert abs(best.C-frozen['C_cal'])<1e-12 and abs(best.gamma-frozen['gamma_cal'])<1e-12,'Refit differs from the recorded selection'
 print(out)
