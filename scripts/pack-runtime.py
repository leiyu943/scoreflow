"""Assemble a relocatable inference-only runtime from an existing marker install.

Usage: python scripts/pack-runtime.py --from-bench PATH --destination PATH
No training datasets, user scores, annotation UI or original virtualenv launchers.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--from-bench', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    args=p.parse_args(); source=args.from_bench.resolve(); dest=args.destination.resolve()
    if dest == source or source in dest.parents: raise ValueError('Choose a destination outside the source runtime.')
    if not (source/'gpu_env/pyvenv.cfg').is_file(): raise ValueError('Expected the existing omr_bench folder.')
    dest.mkdir(parents=True,exist_ok=True)
    skip=shutil.ignore_patterns('__pycache__','*.pyc','.git','.pytest_cache')
    def tree(relative, exclude=()):
        src=source/relative; out=dest/relative
        shutil.copytree(src,out,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.lib','.git','.pytest_cache',*exclude))
        print('Copied',relative,flush=True)
    # Copy the interpreter itself; a venv points back to its creator's machine.
    cfg=dict(line.split(' = ',1) for line in (source/'gpu_env/pyvenv.cfg').read_text().splitlines() if ' = ' in line)
    python=Path(cfg['home']); target=dest/'python'; target.mkdir(exist_ok=True)
    for pattern in ['python.exe','python3.dll','python312.dll','vcruntime*.dll','msvcp*.dll','concrt140.dll','ucrtbase.dll','api-ms-win-*.dll','LICENSE*']:
        for f in python.glob(pattern):
            if f.is_file(): shutil.copy2(f,target/f.name)
    shutil.copytree(python/'Lib',target/'Lib',dirs_exist_ok=True,ignore=shutil.ignore_patterns('site-packages','__pycache__','*.pyc','test','tests','idlelib','ensurepip','tkinter'))
    shutil.copytree(python/'DLLs',target/'DLLs',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','_tkinter.pyd','_ctypes_test.pyd','_test*.pyd'))
    # Conda's standard-library extension DLLs resolve these libraries here.
    for pattern in ['libssl*.dll','libcrypto*.dll','libffi*.dll','ffi*.dll','libexpat.dll','sqlite3.dll','bzip2.dll','libbz2.dll','liblzma.dll','zlib.dll','zstd.dll','libzstd.dll']:
        for directory in [python,python/'Library/bin']:
            for f in directory.glob(pattern): shutil.copy2(f,target/f.name)
    print('Copied standalone Python 3.12',flush=True)
    tree('gpu_env/Lib/site-packages',('pip','pip-*','setuptools','setuptools-*'))
    tree('gpu_runtime_v2/pydeps')
    tree('teacher_candidates/homr465/repo')
    tree('teacher_candidates/homr465/pydeps')
    tree('smt_pydeps',('numpy','numpy-*','numpy.libs'))
    tree('guitar-tab-omr',('assets','metrics'))
    tree('teacher_refinement_v1_20261024/clef_model')
    tree('oemer_env/Lib/site-packages',('pip','pip-*','setuptools','setuptools-*','torch','torch-*','torchvision','torchvision-*','torchgen','functorch','numpy','numpy-*','numpy.libs','onnxruntime','onnxruntime*','cv2','opencv*','PIL','PIL-stubs','pillow-*','matplotlib','matplotlib-*','mpl_toolkits','verovio','verovio*','oemer','oemer-*','tensorflow*','types_tensorflow*','cairosvg','cairosvg-*'))
    reg=json.loads((source/'model_registry.json').read_text(encoding='utf-8'))
    config={'version':reg['version'],'staff_engine':reg['staff_engine'],'device':'cuda','tab_status':'experimental','staff_status':'optimized recognition and correction pipeline'}
    for prefix in ['tab','mixed_tab']:
        src=Path(reg[prefix+'_checkpoint']); rel='models/'+src.name
        if prefix=='mixed_tab' and reg['mixed_tab_checkpoint']!=reg['tab_checkpoint']:rel='models/mixed_'+src.name
        out=dest/rel;out.parent.mkdir(exist_ok=True)
        shutil.copy2(src,out)
        if hashlib.sha256(out.read_bytes()).hexdigest()!=reg[prefix+'_sha256']: raise ValueError('Model checkpoint checksum mismatch')
        config[prefix+'_checkpoint']=rel;config[prefix+'_sha256']=reg[prefix+'_sha256']
    (dest/'model_registry.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    lock=json.loads((source/'gpu_runtime_v2/homr_weights_lock.json').read_text(encoding='utf-8'))
    lock['models']={str(Path(k).relative_to(source)).replace('\\','/'):v for k,v in lock['models'].items()}
    for rel,digest in lock['models'].items():
        if hashlib.sha256((dest/rel).read_bytes()).hexdigest()!=digest:raise ValueError('HOMR weights checksum mismatch')
    (dest/'gpu_runtime_v2/homr_weights_lock.json').write_text(json.dumps(lock,indent=2),encoding='utf-8')
    metadata={'created':datetime.now(timezone.utc).isoformat(),'platform':'windows-x64','python':'3.12','source_datasets_included':False,'model_registry':'model_registry.json'}
    (dest/'runtime-manifest.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    marker=source.parent.parent
    synth=marker/'tools/fluidsynth/fluidsynth-v2.6.0-win10-x64-cpp11/bin'
    sf=marker.parent/'reaper/soundfonts'
    if synth.is_dir() and (sf/'GeneralUser-GS.sf2').is_file():
        shutil.copytree(synth,dest/'audio/fluidsynth',dirs_exist_ok=True)
        for f in sf.glob('GeneralUser-GS*'):shutil.copy2(f,dest/'audio'/f.name)
        for f in (Path(__file__).resolve().parents[1]/'licenses').glob('*.txt'):
            shutil.copy2(f,dest/'audio'/f.name)
        print('Copied seven-instrument GeneralUser GS sampling backend',flush=True)
    else:
        print('Sampling backend missing: provide audio/fluidsynth and audio/GeneralUser-GS.sf2 separately.',flush=True)
    print('Portable runtime complete:',dest,flush=True)

if __name__=='__main__':main()
