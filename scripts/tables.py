"""Derived word-space ratios and principal operating points for Tables 3--5."""
import csv, math
from common import load,ROOT,save
def derived(out):
 rows=load(out/'thresholds.json');expected=load(ROOT/'results/threshold-tables/expected.json')
 lookup={(r['k'],r['ell']):r for r in expected}
 for r in rows:
  ref=lookup[(r['k'],r['ell'])]
  for k in ['c_peel','c_orient']:
   if abs(r[k]-ref[k])>1e-9:raise RuntimeError('Threshold differs from stored value')
  r['peeling_space_ratio']=r['ell']/r['c_peel'] if r['c_peel'] else None
  r['orientability_space_ratio']=r['ell']/r['c_orient'];r['threshold_ratio']=r['c_peel']/r['c_orient']
 with (out/'table3-4.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
 save(out/'table5.json',[r for r in rows if (r['k'],r['ell']) in [(3,1),(2,3),(2,6),(3,4)]])
 save(out/'validation.json',{'entries':len(rows),'matches_stored_thresholds':True,'infinite_peeling_ratio_encoded_as_null':True})
 print(out)
