"""Replay frozen measurement jobs with exact inputs and recorded resource limits."""
import json, subprocess, os, signal, time, statistics, csv
from pathlib import Path
from common import ROOT,save,dataset,sha
from build import build
FIELDS='protocol algorithm success failure logical_bits state_bits control_bits payload_bits update_alice update_bob sender transfer receiver alice_hash bob_hash residual_hash required_symbols payload_sha256 affinity'.split()
def parse(s):
 rows=[]
 for line in s.splitlines():
  if not line.strip():continue
  if line.lstrip().startswith('['):return json.loads(s)
  if line.lstrip().startswith('{'):
   rows.append(json.loads(line));continue
  v=line.split('\t');r=dict(zip(FIELDS,v));assert len(v) in [17,19],(len(v),line)
  for k in ['logical_bits','state_bits','control_bits','payload_bits','required_symbols']:r[k]=int(r[k])
  for k in ['update_alice','update_bob','sender','transfer','receiver']:r[k]=float(r[k])
  r['success']=r['success']=='1';rows.append(r)
 return rows
def execute(cmd,timeout,stdin=None):
 t=time.monotonic();p=subprocess.Popen([str(x) for x in cmd],stdin=subprocess.PIPE if stdin else None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 failure=None
 try:out,err=p.communicate(stdin,timeout=timeout)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate();failure='timeout'
 return {'command':[str(x) for x in cmd],'returncode':p.returncode,'failure':failure or ('process_error' if p.returncode else None),'wall_seconds':time.monotonic()-t,'stdout':out,'stderr':err}
def run(campaign,args,out):
 jobs=[json.loads(s) for s in (ROOT/'scripts/jobs'/(campaign+'.jsonl')).read_text().splitlines()]
 if args.d:jobs=[j for j in jobs if j.get('d')==args.d]
 if args.method:jobs=[j for j in jobs if j['engine']==args.method]
 if args.kind:jobs=[j for j in jobs if j.get('kind', 'timing')==args.kind]
 if args.limit:jobs=jobs[:args.limit]
 if not jobs:raise ValueError('No jobs match this selection')
 if args.dry_run:
  print(json.dumps({'campaign':campaign,'jobs':len(jobs),'engines':sorted({j['engine'] for j in jobs}),'first_job':jobs[0]},indent=2));return
 save(out/'protocol.json',{'campaign':campaign,'smoke':args.smoke,'jobs':len(jobs),'cpu':args.cpu,'workers':args.workers,'memory_limit_bytes':85899345920,'input_generation_and_truth_check_outside_timing':True,'job_file_sha256':sha(ROOT/'scripts/jobs'/(campaign+'.jsonl')),'timing_policy':'one worker per pinned core; use workers=1 for reported timing'})
 exes={j['engine']:build(j['engine']) for j in jobs}
 # Resolve and hash each input once; all repeats reuse that verified file.
 inputs={}
 for j in jobs:
  if j['dataset'] not in inputs:inputs[j['dataset']]=dataset(j['dataset'],args.data_root,out,args.smoke)
 cpus=sorted(os.sched_getaffinity(0));assert args.cpu in cpus,'Requested CPU is unavailable'
 def worker(item):
  index,j=item;p=inputs[j['dataset']];a=[str(p) if v=='{dataset}' else v for v in j['args']]
  if args.smoke and j['engine']=='rateless':a[-1]=sha(p)
  cpu=cpus[(cpus.index(args.cpu)+index%args.workers)%len(cpus)]
  memory=j.get('memory_limit_bytes',8589934592 if j['engine'].startswith('fingerprint-') else 85899345920)
  cmd=['prlimit','--as='+str(memory),'--','taskset','-c',str(cpu),str(exes[j['engine']])]+a
  r=execute(cmd,j['timeout']);result=[];issues=[]
  if r['returncode']==0:
   try:result=parse(r['stdout'])
   except Exception as e:issues.append('parse_error: '+str(e))
  if not args.smoke and result:
   if j.get('expected_rows'):
    oldrows=j['expected_rows']
    if len(oldrows)!=len(result):issues.append('reference_mismatch: output row count')
    for current,old in zip(result,oldrows):
     for k in ['success','failure','payload_bits','logical_bits','alice_hash','bob_hash','status','bytes','symbols']:
      if k in old and current.get(k)!=old[k]:issues.append('reference_mismatch: '+k)
   expected=j.get('expected')
   if expected and j['engine'] not in ['fingerprint-100000','fingerprint-1000000']:
    current=result[0]
    for k in ['success','failure','payload_bits','alice_hash','bob_hash']:
     if k in expected and current.get(k)!=expected[k]:issues.append('reference_mismatch: '+k)
   if j['engine']=='rateless':
    for x in result:
     if x.get('status')=='success' and not all(x.get(k) for k in ['truth_verified','counts_identical','accounting_exact']):issues.append('rateless_validation_failed')
   if j.get('expected_paper'):
    expected=j['expected_paper'];current=result[0]
    for old,new in [('success','success'),('failure_reason','failure'),('total_payload_bits','payload_bits'),('alice_output_sha256','alice_hash'),('bob_output_sha256','bob_hash')]:
     if old in expected and current.get(new)!=expected[old]:issues.append('paper_reference_mismatch: '+old)
  rec={'job':j,'execution':r,'results':result,'validation_issues':issues,'smoke':args.smoke}
  save(out/'records'/('%06d.json'%index),rec);return rec
 if args.workers==1:records=[worker(v) for v in enumerate(jobs)]
 else:
  from concurrent.futures import ThreadPoolExecutor
  with ThreadPoolExecutor(args.workers) as pool:records=list(pool.map(worker,enumerate(jobs)))
 raw=[];info_map=json.loads((ROOT/'scripts/inputs.json').read_text())
 for r in records:
  if not r['results']:
   raw.append({'engine':r['job']['engine'],'d':r['job']['d'],'trial':r['job']['trial'],'job':r['job']['id'],'config_id':r['job'].get('config_id',''),'success':False,'status':r['execution']['failure'] or 'parse_error'})
  for result in r['results']:
   n=max(200,r['job']['d']) if args.smoke else info_map[r['job']['dataset']]['N']
   result=dict(result)
   if all(k in result for k in ['update_alice','update_bob','sender','transfer','receiver']):
    result['update_ns_per_input']=(result['update_alice']+result['update_bob'])*1e9/(2*n)
    result['full_decode_s']=result['sender']+result['transfer']+result['receiver']
   elif all(k in result for k in ['alice_ingest_cpu_s','bob_ingest_cpu_s','alice_generate_cpu_s','bob_receive_cpu_s','wire_encode_cpu_s','wire_decode_cpu_s']):
    result['update_ns_per_input']=(result['alice_ingest_cpu_s']+result['bob_ingest_cpu_s'])*1e9/(2*n)
    result['full_decode_s']=sum(result[k] for k in ['alice_generate_cpu_s','bob_receive_cpu_s','wire_encode_cpu_s','wire_decode_cpu_s'])
   if 'full_decode_s' in result:result['full_decode_us_per_difference']=result['full_decode_s']*1e6/r['job']['d']
   if 'payload_bits' in result:result['communication_ratio']=result['payload_bits']/(30*r['job']['d'])
   raw.append({'engine':r['job']['engine'],'d':r['job']['d'],'trial':r['job']['trial'],'job':r['job']['id'],'config_id':r['job'].get('config_id',r['job']['args'][-1] if r['job']['engine'].startswith('paper-') else ''),**result})
 keys=sorted({k for r in raw for k in r})
 with (out/'raw.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,keys);w.writeheader();w.writerows(raw)
 groups=[]
 def group(r):return (r['engine'],r['d'],str(r.get('config_id','')),str(r.get('algorithm','')),str(r.get('fingerprint_bits','')))
 for key in sorted({group(r) for r in raw}):
  eng,d,cid,codec,bits=key;rr=[r for r in raw if group(r)==key];g={'engine':eng,'d':d,'config_id':cid,'codec':codec,'fingerprint_bits':bits,'observations':len(rr),'successes':sum(r.get('success',r.get('status')=='success') for r in rr)}
  for key in ['payload_bits','bytes','ratio','symbols','update_alice','update_bob','sender','transfer','receiver']:
   successful=[r for r in rr if r.get('success',r.get('status')=='success')]
   v=[r[key] for r in successful if isinstance(r.get(key),(int,float))]
   if v:g[key+'_mean']=statistics.mean(v)
  # Dataset means are the unit of timing uncertainty; repetitions are not independent inputs.
  for key in ['update_ns_per_input','full_decode_s','full_decode_us_per_difference','update_alice','update_bob','sender','transfer','receiver','alice_ingest_cpu_s','bob_ingest_cpu_s','alice_generate_cpu_s','bob_receive_cpu_s','wire_encode_cpu_s','wire_decode_cpu_s']:
   by_trial={}
   for r in successful:
    if isinstance(r.get(key),(int,float)):by_trial.setdefault(r['trial'],[]).append(r[key])
   means=[statistics.mean(v) for v in by_trial.values()]
   if means:
    import random
    rng=random.Random(20261007);samples=sorted(statistics.mean(rng.choices(means,k=len(means))) for _ in range(10000))
    g[key]={'mean':statistics.mean(means),'ci95':[samples[249],samples[9749]],'dataset_means':means}
  groups.append(g)
 save(out/'summary.json',groups)
 validation={'jobs':len(records),'process_failures':sum(bool(r['execution']['failure']) for r in records),'reference_mismatches':sum(bool(r['validation_issues']) for r in records),'smoke':args.smoke,'formal_results':not args.smoke}
 save(out/'validation.json',validation);print(json.dumps({'output':str(out),**validation},indent=2))
 if validation['reference_mismatches']:raise RuntimeError('Reference validation failed; inspect retained records')
