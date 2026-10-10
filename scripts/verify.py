"""Check result coverage, source hashes, codecs and byte accounting without rerunning campaigns."""
import json,csv,collections
from common import ROOT,verify_sources,load
def verify():
 verify_sources();inputs=load(ROOT/'scripts/inputs.json');campaigns={}
 for p in (ROOT/'scripts/jobs').glob('*.jsonl'):
  jobs=[json.loads(x) for x in p.read_text().splitlines()]
  assert jobs and all(j['dataset'] in inputs for j in jobs)
  campaigns[p.stem]=len(jobs)
 assert len(load(ROOT/'results/sharp/summary.json'))==117
 raw=list(csv.DictReader((ROOT/'results/rateless/raw-samples.csv').open()));assert len(raw)==1035
 for r in raw:
  bits=sum(int(r[k]) for k in ['symbol_bits','hash_bits','padding_bits'])+8*sum(int(r[k]) for k in ['count_bytes','metadata_bytes','ack_bytes'])
  assert bits==8*int(r['bytes']);assert abs(bits/(30*int(r['d']))-float(r['ratio']))<1e-12
  assert all(r[k]=='True' for k in ['truth_verified','counts_identical','accounting_exact'])
 for d in [100000,1000000]:
  rows=load(ROOT/'results/fingerprint'/str(d)/'summary.json');assert len(rows)==27 and all(r['trials']==100 for r in rows)
 print(json.dumps({'passed':True,'source_hashes_verified':True,'input_manifest_entries':len(inputs),'campaign_jobs':campaigns,'rateless_accounting_rows':len(raw),'fingerprint_observations':5400,'formal_campaigns_rerun':False},indent=2))
