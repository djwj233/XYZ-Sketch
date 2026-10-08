"""Regenerate paper plots from measured data. This command does not rerun trials."""
from pathlib import Path
import json,csv,collections
from common import ROOT,load,save
def plot(out):
 import numpy as np
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'svg.fonttype':'none'})
 assets=[]
 def emit(fig,name):
  p=out/name;p.parent.mkdir(parents=True,exist_ok=True)
  for ext in ['pdf','png','svg']:fig.savefig(str(p)+'.'+ext,bbox_inches='tight',dpi=200)
  assets.append(name);plt.close(fig)
 def wilson(s,n):
  z=1.959963984540054;p=s/n;a=1+z*z/n;b=(p+z*z/(2*n))/a;h=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/a;return max(0,b-h),min(1,b+h)
 rows=[json.loads(s) for s in (ROOT/'results/reference/threshold/aggregate.jsonl').read_text().splitlines()]
 fig,axs=plt.subplots(1,3,figsize=(12,3.3))
 for ax,(k,l) in zip(axs,[(2,3),(2,6),(3,4)]):
  for mode,name in [('iid','i.i.d.'),('naive','Standard SC'),('circular','Circular SC')]:
   rr=sorted([r for r in rows if (r['k'],r['ell'],r['mode'])==(k,l,mode)],key=lambda r:r['M']);x=[r['R_w30'] for r in rr];y=[r['success_rate'] for r in rr];ci=[wilson(r['successes'],r['trials']) for r in rr]
   line,=ax.plot(x,y,label=name);ax.fill_between(x,[v[0] for v in ci],[v[1] for v in ci],color=line.get_color(),alpha=.14)
  ax.set(xlabel='Communication ratio',ylabel='Success probability',title=f'k={k}, ell={l}',ylim=(-.03,1.03));ax.legend(fontsize=8)
 emit(fig,'paper/figure1a')
 hm=list(csv.DictReader((ROOT/'results/reference/heatmaps.csv').open()));panels=sorted({(int(r['d']),int(r['M'])) for r in hm})
 def heat(ax,d,m):
  rr=[r for r in hm if (int(r['d']),int(r['M']))==(d,m)];aa=sorted({float(r['a']) for r in rr});zz=sorted({int(r['z']) for r in rr});mat=np.zeros((len(zz),len(aa)))
  for r in rr:mat[zz.index(int(r['z'])),aa.index(float(r['a']))]=float(r['success_rate'])
  im=ax.imshow(mat,origin='lower',vmin=0,vmax=1,cmap='Blues',aspect='auto');ax.set_xticks(range(len(aa)));ax.set_xticklabels([f'{a:.2f}' for a in aa],rotation=35);ax.set_yticks(range(len(zz)));ax.set_yticklabels(zz);ax.set(xlabel='a',ylabel='z',title=f'd={d:,}, M={m:,}')
  from matplotlib.patches import Rectangle
  for r in rr:
   if r['is_frozen_prediction']=='True':ax.add_patch(Rectangle((aa.index(float(r['a']))-.45,zz.index(int(r['z']))-.45),.9,.9,fill=False,edgecolor='#f0c500',linewidth=2))
  return im
 for name,(d,m) in zip(['figure1b','figure1c'],[(3000,596),(10000,1948)]):
  fig,ax=plt.subplots(figsize=(4.5,3.6));im=heat(ax,d,m);fig.colorbar(im,ax=ax,label='Success probability');emit(fig,'paper/'+name)
 fig,axs=plt.subplots(6,2,figsize=(11,23),constrained_layout=True)
 for ax,(d,m) in zip(axs.flat,panels):im=heat(ax,d,m)
 fig.colorbar(im,ax=axs,label='Success probability',shrink=.5);emit(fig,'paper/figure3')
 fig,axs=plt.subplots(2,2,figsize=(11,8),constrained_layout=True)
 for ax,(d,m) in zip(axs.flat,[(3000,596),(3000,621),(100000,18155),(100000,18940)]):im=heat(ax,d,m)
 fig.colorbar(im,ax=axs,label='Success probability');emit(fig,'optimized/supplementary-heatmaps')
 pts=load(ROOT/'results/paper/aggregate.json')['points'];names={'xyz':'XYZ-Sketch (unoptimized)','external_iblt':'IBLT','riblt':'Rateless (fixed-prefix adapter)','minisketch':'MiniSketch','cpisync':'CPISync'}
 for metric,label,stem in [('R_w30','Communication ratio','figure2a'),('update_ns_per_input_conditional_mean','Update (ns/input)','figure2b'),('decode_ns_per_difference_conditional_mean','Decode (ns/difference)','figure2c')]:
  fig,ax=plt.subplots(figsize=(5,3.6))
  for alg,name in names.items():
   rr=sorted([p for p in pts if p['algorithm']==alg and p.get(metric) is not None],key=lambda p:p['d']);ax.plot([p['d'] for p in rr],[p[metric] for p in rr],marker='o',markersize=3,label=name)
  ax.set(xscale='log',xlabel='Difference size d',ylabel=label)
  if metric!='R_w30':ax.set_yscale('log')
  ax.legend(fontsize=7);emit(fig,'paper/'+stem)
 # Accepted GF(2^30) evaluation, kept separate from earlier prime-field comparisons.
 sf=ROOT/'results/optimized/plotted-series.json'
 if sf.exists():
  series=load(sf)
  for metric,label in [('communication','Communication ratio'),('update','Update (ns/input)'),('decode','Decode (us/difference)')]:
   fig,ax=plt.subplots(figsize=(5.5,3.6))
   for name,ss in series.items():
    rr=sorted(ss[metric]);ax.plot([r[0] for r in rr],[r[1] for r in rr],marker='o',markersize=3,label=name)
    for d,v,ci in rr:
     if ci:ax.errorbar(d,v,yerr=[[max(0,v-ci[0])],[max(0,ci[1]-v)]],fmt='none',capsize=2)
   ax.set(xscale='log',xlabel='Difference size d',ylabel=label)
   if metric!='communication':ax.set_yscale('log')
   ax.legend(fontsize=7);emit(fig,'optimized/'+metric)
 rr=load(ROOT/'results/sharp/summary.json');fig,ax=plt.subplots(figsize=(5.5,3.6))
 for mode in ['iid','naive','circular']:
  r=sorted([r for r in rr if r['mode']==mode],key=lambda r:r['R_w30']);ax.plot([r['R_w30'] for r in r],[r['success_rate'] for r in r],label=mode)
 ax.set(xlabel='Communication ratio',ylabel='Success probability');ax.legend();emit(fig,'optimized/sharp-threshold')
 fig,ax=plt.subplots(figsize=(6,3.6))
 for d in [100000,1000000]:
  rr=load(ROOT/'results/fingerprint'/str(d)/'summary.json');x=[r['fingerprint_bits'] for r in rr];y=[r['success_rate'] for r in rr];line,=ax.plot(x,y,marker='o',label=f'd={d:,}');ax.fill_between(x,[r['wilson95_low'] for r in rr],[r['wilson95_high'] for r in rr],color=line.get_color(),alpha=.15)
 ax.set(xlabel='Fingerprint bits',ylabel='Success probability');ax.legend();emit(fig,'optimized/fingerprint-two-scales')
 # Parameter curves are generated from frozen measured points, not simulation.
 points=load(ROOT/'results/optimized/figure-data.json')['parameters']
 ext=ROOT/'results/parameters/plot-data.json'
 if ext.exists():points+=load(ext)
 for metric,ylabel in [('update_ns_per_input','Update (ns/input)'),('full_decode_s','Full decode (seconds)')]:
  fig,ax=plt.subplots(figsize=(5.5,3.6))
  for k in [2,3]:
   rr=sorted([r for r in points if r['method']=='xyz' and r['d']==100000 and r['k']==k],key=lambda r:r['ell']);ax.plot([r['R'] for r in rr],[r['metrics'][metric]['mean'] for r in rr],marker='o',label=f'k={k}')
   for r in rr:ax.annotate(str(r['ell']),(r['R'],r['metrics'][metric]['mean']),xytext=(3,3),textcoords='offset points')
  ax.set(xlabel='Communication ratio',ylabel=ylabel);ax.legend();emit(fig,'optimized/parameters-'+metric)
 # Field-level communication at d=100,000, using each implementation's own codec.
 components=[];d=100000
 xyz=next(r for r in load(ROOT/'results/optimized/timing.json') if r['d']==d and r['method']=='xyz' and r['main_curve'])
 cells=xyz['source_actual']['M'];data=30*xyz['source_actual']['ell']*cells;v=xyz['result']
 components.append(('XYZ',data,0,v['logical_bits']-data,v['payload_bits']-v['logical_bits']))
 compact=load(ROOT/'results/compact-iblt/timing.json')
 for algorithm,label in [('external_iblt','IBLT'),('iblt_sc','IBLT+SC')]:
  matched=[r for r in compact if r['actual']['d']==d and r['actual']['algorithm']==algorithm];m=matched[0]['actual']['M']
  values=[v for r in matched for v in r['rows'] if v['algorithm']=='compact_count'];count=np.mean([v['logical_bits']-62*m for v in values]);padding=np.mean([v['payload_bits']-v['logical_bits'] for v in values])
  components.append((label,30*m,32*m,count,padding))
 rateless=next(r for r in load(ROOT/'results/rateless/summary.json') if r['d']==d)['communication']
 components.append(('Rateless',rateless['symbol_bits']['mean'],rateless['hash_bits']['mean'],8*rateless['count_bytes']['mean'],8*(rateless['metadata_bytes']['mean']+rateless['ack_bytes']['mean'])+rateless['padding_bits']['mean']))
 final_components=[r for r in components if r[0]!='Rateless']
 fig,ax=plt.subplots(figsize=(6.5,3.6));bottom=np.zeros(len(final_components))
 for i,label in enumerate(['Data','Checksum','Count','Metadata/padding'],1):
  values=np.array([r[i] for r in final_components])/(30*d);ax.bar([r[0] for r in final_components],values,bottom=bottom,label=label);bottom+=values
 ax.set_ylabel('Communication ratio');ax.legend(fontsize=8);emit(fig,'optimized/figure2e-communication-breakdown')
 fig,ax=plt.subplots(figsize=(6.5,3.6));bottom=np.zeros(len(components))
 for i,label in enumerate(['Data','Checksum','Count','Metadata/padding'],1):
  values=np.array([r[i] for r in components])/(30*d);ax.bar([r[0] for r in components],values,bottom=bottom,label=label);bottom+=values
 ax.set_ylabel('Communication ratio');ax.legend(fontsize=8);emit(fig,'optimized/communication-breakdown')
 save(out/'communication-breakdown.json',{'d':d,'components_bits':components,'field_names':['label','data','checksum','count','metadata_padding']})
 save(out/'manifest.json',{'assets':assets,'measurements_rerun':False,'source':'stored measured results; paper and optimized campaigns are separate'});print(out)
