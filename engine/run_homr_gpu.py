"""HOMR 465, batch 1, official FP16 weights, supervised CUDA execution.

Use gpu_env/Scripts/python.exe run_homr_gpu.py IMAGE [--profile].
Every ONNX session is explicitly constructed with CUDA and verified.
"""
import argparse
from collections import Counter
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import time
from gpu_guard import bootstrap,cuda_options,require_cuda_session,BUDGET_MIB,cool_between_patches

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('image',type=Path)
parser.add_argument('--profile',action='store_true')
cli=parser.parse_args()
if not cli.image.is_file() or cli.image.suffix.lower() not in {'.png','.jpg','.jpeg'}:
    parser.error('Provide one PNG/JPEG image; images are processed sequentially.')
bootstrap('cuda')
from runtime_paths import activate_gpu as activate, RUNTIME as B
activate()
os.environ.update(OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
import torch
import onnxruntime as ort
import cv2
import hashlib
weights=json.loads((B/'gpu_runtime_v2/homr_weights_lock.json').read_text(encoding='utf-8'))['models']
for path,digest in weights.items():
    if hashlib.sha256((B/Path(path)).read_bytes()).hexdigest()!=digest:raise RuntimeError('Pinned GPU weights changed')
ort.preload_dlls()
cv2.setNumThreads(4)
if 'CUDAExecutionProvider' not in ort.get_available_providers():
    raise RuntimeError('CUDA provider unavailable; no CPU fallback.')
run_dir=Path(os.environ['OMR_GPU_RUN_DIR'])
staged=run_dir/cli.image.name
shutil.copyfile(cli.image,staged)
original=ort.InferenceSession
sessions=[]
session_failed=False


def session(path,*args,**kwargs):
    global session_failed
    if session_failed:raise RuntimeError('Previous CUDA initialization failed; retries disabled.')
    options=cuda_options()
    # The decoder retains weights plus a growing KV cache; equal division
    # starves it even when the card has ample free memory.
    model_name=Path(path).name
    budget=1920 if model_name.startswith('decoder_') else 768 if model_name.startswith('encoder_') else 384
    options['gpu_mem_limit']=budget*1024**2
    # KV tensors grow every token. Separate exact-sized allocations accumulate
    # unusable chunks; allocate reusable larger arena blocks within the cap.
    if model_name.startswith('decoder_'):options['arena_extend_strategy']='kNextPowerOfTwo'
    opts=ort.SessionOptions()
    opts.intra_op_num_threads=4;opts.inter_op_num_threads=1
    opts.enable_mem_pattern=False
    opts.enable_profiling=cli.profile
    opts.profile_file_prefix=str(run_dir/('profile_'+Path(path).stem))
    kwargs.update(sess_options=opts,enable_fallback=False,
                  providers=[('CUDAExecutionProvider',options),'CPUExecutionProvider'])
    try:
        value=original(path,*args,**kwargs)
        require_cuda_session(value)
    except Exception:
        session_failed=True
        raise
    sessions.append((str(path),value))
    print('Verified CUDA session:',Path(path).name,flush=True)
    return value


ort.InferenceSession=session
from homr import main as homr_main
import homr.segmentation.inference_segnet as segnet
from teacher_image_refinement import OctaveClefDetector
from simple_event_rules import correct_events
original_infer=segnet.inference
signature=inspect.signature(original_infer)


def inference(*args,**kwargs):
    bound=signature.bind(*args,**kwargs)
    bound.arguments['batch_size']=1
    return original_infer(*bound.args,**bound.kwargs)


segnet.inference=inference
original_patch_run=segnet.Segnet.run


def patch_run(self,data):
    cool_between_patches()
    started=time.perf_counter()
    result=original_patch_run(self,data)
    time.sleep(max(.01,time.perf_counter()-started))
    return result


segnet.Segnet.run=patch_run
cue=OctaveClefDetector(B/'teacher_refinement_v1_20261024/clef_model').predict(staged)


def generate(arguments,staffs,title):
    result,audit=correct_events(staffs,arguments,cue,title)
    audit.update(runtime='CUDA',precision='FP16',batch_size=1,
        ort_version=ort.__version__,torch_version=torch.__version__,
        sessions=[{'model':p,'providers':s.get_providers()} for p,s in sessions])
    (run_dir/'event_rules_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


homr_main.generate_xml=generate
sys.argv=['homr',str(staged),'--gpu','force','--no-title']
start=time.perf_counter()
homr_main.main()
if len(sessions)!=3:raise RuntimeError('Expected exactly segnet, encoder and decoder sessions.')
profiles=[]
if cli.profile:
    for path,value in sessions:
        profile=Path(value.end_profiling())
        nodes=[r for r in json.loads(profile.read_text(encoding='utf-8'))
               if r.get('cat')=='Node' and r.get('args',{}).get('provider')]
        counts=Counter(r['args']['provider'] for r in nodes)
        if not counts['CUDAExecutionProvider']:raise RuntimeError('No CUDA kernels observed: '+path)
        profiles.append({'model':path,'file':str(profile),'kernel_counts_by_provider':dict(counts),
            'cpu_op_types':dict(Counter(r['args'].get('op_name','?') for r in nodes
                if r['args']['provider']=='CPUExecutionProvider'))})
report={'status':'passed','runtime':'CUDA','precision':'FP16','batch_size':1,
    'seconds':time.perf_counter()-start,'ort':ort.__version__,
    'prediction':str(staged.with_suffix('.musicxml')),'profiles':profiles}
(run_dir/'homr_result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
