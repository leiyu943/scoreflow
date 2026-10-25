"""Guarded batch worker for TAB chunks.

The old gateway launched one CUDA supervisor/model process per visual chunk.
This worker loads the accepted Tabbox checkpoint once and decodes all chunks in
one guarded CUDA session.  It deliberately does not create unbounded CUDA
workers: the project GPU guard exists to prevent the black-screen failure mode.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from gpu_guard import bootstrap, configure_torch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
parser.add_argument('--batch-manifest', type=Path, required=True)
parser.add_argument('--output-root', type=Path, required=True)
parser.add_argument('--checkpoint', type=Path, required=True)
args_cli = parser.parse_args()

bootstrap(args_cli.device)
if args_cli.device == 'cuda':
    from runtime_paths import activate_gpu as activate
    activate()

from runtime_paths import RUNTIME as B
sys.path.append(str(B / 'oemer_env/Lib/site-packages'))
sys.path.insert(0, str(B / 'smt_pydeps'))
sys.path.insert(0, str(B / 'guitar-tab-omr/scripts'))

import numpy as np
import torch
from PIL import Image, ImageOps
from guitar_omr_eval import create_model, greedy_decode, decode_ids, build_token_groups

torch.set_num_threads(4)
torch.set_num_interop_threads(1)
if args_cli.device == 'cuda':
    configure_torch(torch)
device = torch.device(args_cli.device)

manifest = json.loads(args_cli.batch_manifest.read_text(encoding='utf-8'))
if not isinstance(manifest, list) or not manifest:
    raise ValueError('Batch manifest must contain at least one TAB chunk.')

checkpoint = args_cli.checkpoint.resolve()
ck = torch.load(checkpoint, map_location='cpu', weights_only=False)
model_args = dict(ck['config']['args'])
model_args['pretrained_encoder'] = False
model = create_model(model_args, ck['vocab'], ck['config'])
model.load_state_dict(ck['model'])
model.to(device).eval()

vocab = ck['vocab']
idtok = {int(i): token for token, i in vocab.items()}
groups = build_token_groups(vocab)

if args_cli.device == 'cuda':
    from gpu_guard import cool_between_patches

    def before_decode(module, inputs):
        cool_between_patches(check_interval=.2, pause_c=60, resume_c=55)

    model.register_forward_pre_hook(before_decode)

def decode_one(job):
    sid = str(job['sid'])
    if Path(sid).name != sid or sid in {'.', '..'}:
        raise ValueError('Invalid TAB chunk id: ' + sid)
    input_image = Path(job['input_image']).resolve()
    output_root = Path(job.get('output_root', args_cli.output_root)).resolve()
    output_dir = output_root / sid
    output_dir.mkdir(parents=True, exist_ok=True)
    hint = job.get('initial_meter')
    if hint in (None, '', 'auto'):
        initial_meter = None
    else:
        initial_meter = tuple(int(x) for x in str(hint).split('/'))
        if len(initial_meter) != 2 or min(initial_meter) <= 0:
            raise ValueError('Invalid initial meter for ' + sid)
    with Image.open(input_image) as source:
        im = ImageOps.contain(source.convert('L'), (1200, 224), method=Image.Resampling.LANCZOS)
    canvas = Image.new('L', (1200, 224), 255)
    canvas.paste(im, (0, 0))
    x = torch.from_numpy((1 - np.asarray(canvas, dtype=np.float32) / 255)[None, :, :].copy()).to(device)
    started = time.perf_counter()
    with torch.inference_mode():
        pred, eos = greedy_decode(model, x, vocab['<BOS>'], vocab['<EOS>'], 384, device, idtok, groups, initial_meter)
    tokens = decode_ids(pred, idtok)
    result = {
        'engine': 'tabbox', 'id': sid, 'tokens': tokens,
        'seconds': time.perf_counter() - started, 'load_seconds': 0.0,
        'truncated': not eos, 'device': str(device),
        'initial_meter_hint': initial_meter,
        'checkpoint': str(checkpoint), 'batch_worker': True,
    }
    if args_cli.device == 'cuda':
        torch.cuda.synchronize()
        result.update(
            parameter_devices=sorted({str(parameter.device) for parameter in model.parameters()}),
            cuda_peak_allocated_mib=torch.cuda.max_memory_allocated() / 1024**2,
            torch_version=torch.__version__,
        )
    (output_dir / 'tabbox.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return {key: value for key, value in result.items() if key != 'tokens'}

for index, job in enumerate(manifest, 1):
    summary = decode_one(job)
    print(json.dumps({'batch_index': index, 'batch_total': len(manifest), **summary}, ensure_ascii=False), flush=True)

