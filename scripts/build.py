"""Build only the requested frozen implementation; no network downloads."""
from pathlib import Path
import subprocess, os, sys, argparse
from common import ROOT,go,save,verify_sources,sha
A=ROOT/'algorithms';B=ROOT/'results/build'
def build(name):
 verify_sources();B.mkdir(parents=True,exist_ok=True);target=B/({'dataset':'dataset-portable-v1','prime-threshold':'prime-threshold-portable-v1'}.get(name,name))
 if target.exists():return target
 cmd=['g++','-O3','-DNDEBUG','-std=gnu++17','-w'];src=[];inc=[];libs=['-lcrypto'];ref=A/'baselines/reference';paper=A/'baselines/paper'
 if name in ['xyz','xyz-ell10']:
  p=A/'XYZ-Sketch-optimized/src';src=[p/('xyz_gf230_engine.cpp' if name=='xyz' else 'xyz_gf230_engine_ell10.cpp')];cmd+=['-mpclmul','-DXYZ_TABLE_SQUARES','-DXYZ_DYNAMIC_RECON']
 elif name=='prime-threshold':src=[ROOT/'scripts/threshold_engine.cpp'];inc=[A/'XYZ-Sketch-unoptimized']
 elif name=='ideal-cell':src=[A/'simulators/ideal_cell.cpp'];libs+=['-pthread']
 elif name in ['rateless','rateless-fixed','paper-rateless']:
  p=A/'baselines'/('rateless' if name=='rateless' else 'reference/riblt' if name=='rateless-fixed' else 'paper/riblt')
  files=['main-v2.go','representative-v2.go'] if name=='rateless' else ['main.go']+(['provenance.go'] if (p/'provenance.go').exists() else [])
  cmd=[go(),'build','-o',str(target)]+files
  subprocess.run(cmd,cwd=p,env=dict(os.environ,GOPROXY='off'),check=True)
  save(B/(target.name+'.json'),{'command':cmd,'binary_sha256':sha(target)});return target
 elif name=='iblt-compact':
  p=A/'baselines/iblt-compact';src=[p/x for x in ['engine.cpp','iblt.cpp','compact_count.cpp','murmurhash3.cpp']]
 elif name.startswith('fingerprint-'):
  p=A/'baselines'/name;src=[p/x for x in ['engine.cpp','iblt.cpp','murmurhash3.cpp']]
 elif name=='dataset':src=[ROOT/'scripts/dataset_engine.cpp']
 else:
  ispaper=name.startswith('paper-');p=paper if ispaper else ref;n=name.removeprefix('paper-') if hasattr(str,'removeprefix') else (name[6:] if ispaper else name)
  names={'xyz':'xyz_engine.cpp','xyz-prime':'xyz_engine.cpp','iblt':'external_iblt_engine.cpp','iblt-sc':'sc_engine.cpp','minisketch':'minisketch_engine.cpp','cpisync':'cpisync_engine.cpp'}
  if n not in names:raise ValueError('Unknown build target '+name)
  src=[p/names[n]];inc=[p]
  if n in ['xyz','xyz-prime']:inc+=[A/'XYZ-Sketch-unoptimized']
  if n in ['iblt','iblt-sc']:src += [p/'iblt.cpp',p/'murmurhash3.cpp']
  if (p/'provenance.cpp').exists():src +=[p/'provenance.cpp']
  if n=='minisketch':
   dep=A/'dependencies/minisketch';inc +=[dep/'include']
   src+=[dep/'src/minisketch.cpp']+[dep/'src/fields'/(backend+'_'+str(i)+suffix+'.cpp') for backend in ['generic','clmul'] for i,suffix in [(1,'byte'),(2,'bytes'),(3,'bytes'),(4,'bytes'),(5,'bytes'),(6,'bytes'),(7,'bytes'),(8,'bytes')]]
   cmd+=['-mpclmul','-DHAVE_CLMUL','-DHAVE_CLZ']+['-DDISABLE_FIELD_'+str(i) for i in range(2,65) if i!=30]
  if n=='cpisync':
   dep=A/'dependencies/cpisync';inc +=[dep/'include'];cmd[3]='-std=gnu++11';cmd+=['-DDEFAULT_LOGLEVEL=TEST']
   src +=[dep/'src'/x for x in ['CommString.cpp','Communicant.cpp','CPISync.cpp','DataObject.cpp','Logger.cpp','SyncMethod.cpp','UID.cpp','IBLT.cpp','StrataEst.cpp']];libs+=['-lntl','-lgmp','-pthread']
 cmd += [str(p) for p in src]+['-I'+str(p) for p in inc]+libs+['-o',str(target)]
 subprocess.run(cmd,check=True);save(B/(target.name+'.json'),{'command':cmd,'binary_sha256':sha(target)});return target
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('targets',nargs='*',default=['xyz']);args=p.parse_args()
 for n in args.targets:print(build(n))
