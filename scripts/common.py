"""Shared paths, input verification and fresh output directories."""
from pathlib import Path
import json, hashlib, subprocess, os, datetime, uuid, shutil
ROOT=Path(__file__).resolve().parent.parent
def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2,allow_nan=False)
def fresh(name,out=None):
 p=Path(out).resolve() if out else ROOT/'results/runs'/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+name+'-'+uuid.uuid4().hex[:6])
 p.mkdir(parents=True,exist_ok=False);return p
def go():return os.environ.get('GO') or ('/usr/local/go1.21/bin/go' if Path('/usr/local/go1.21/bin/go').exists() else shutil.which('go') or 'go')
def verify_sources():
 for name,digest in load(ROOT/'results/source-manifest.json').items():
  if sha(ROOT/name)!=digest:raise RuntimeError('Source hash mismatch: '+name)
def dataset(key,data_root,out,small=False):
 info=load(ROOT/'scripts/inputs.json')[key]
 if small:
  token=hashlib.sha256(key.encode()).hexdigest()[:12];p=out/'inputs'/('smoke-'+token+'.bin');N=max(200,info['d'])
 else:p=Path(data_root)/key;N=info['N']
 if p.exists():
  if not small and info['sha256'] and sha(p)!=info['sha256']:raise RuntimeError('Input hash mismatch: '+str(p))
  return p
 from build import build
 exe=build('dataset');p.parent.mkdir(parents=True,exist_ok=True)
 seed=info['seeds'];cmd=[str(exe),str(p),'full',str(info['d']),str(N)]+[str(seed[k]) for k in ['identity','alice_order','bob_order']]
 r=subprocess.run(cmd,text=True,capture_output=True,check=True);meta=json.loads(r.stdout)
 digest=sha(p)
 if not small:
  if info['sha256'] and digest!=info['sha256']:raise RuntimeError('Regenerated input hash mismatch: '+key)
  for k,v in info.get('expected_metadata',{}).items():
   if k in meta and v!=meta[k]:raise RuntimeError('Regenerated dataset metadata differs: '+key+' '+k)
 save(out/'input-receipts'/(hashlib.sha256(key.encode()).hexdigest()+'.json'),{'input':key,'path':str(p),'sha256':digest,'expected_sha256':info['sha256'],'smoke_input':small,'metadata':meta,'generation':cmd})
 return p
