"""Download an external Windows inference runtime; never bundle it into source."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def download(url, target, expected):
    if target.is_file() and digest(target) == expected:
        print('已校验，复用：' + target.name, flush=True)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + '.part')
    for attempt in range(3):
        try:
            print('下载：' + url, flush=True)
            request = urllib.request.Request(url, headers={'User-Agent': 'ScoreFlow/0.2.0'})
            with urllib.request.urlopen(request, timeout=60) as response, part.open('wb') as out:
                total = int(response.headers.get('Content-Length', 0))
                size = 0
                last = time.monotonic()
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
                    size += len(chunk)
                    if time.monotonic() - last > 5:
                        print(f'  {size / 1048576:.1f} MiB' + (f' / {total / 1048576:.1f} MiB' if total else ''), flush=True)
                        last = time.monotonic()
            if digest(part) != expected:
                raise RuntimeError('SHA-256 校验失败：' + target.name)
            part.replace(target)
            return target
        except (OSError, RuntimeError) as exc:
            if attempt == 2:
                raise
            print(f'下载未完成，将重试：{exc}', flush=True)
            time.sleep(2)


def extract_selected(archive, destination, select):
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            if item.is_dir():
                continue
            relative = select(PurePosixPath(item.filename))
            if relative is None:
                continue
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('压缩资源包含非法路径。')
            target = destination.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('资源路径越界。')
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as src, target.open('wb') as out:
                shutil.copyfileobj(src, out)


def interpreter(root):
    for rel in ('python/python.exe', 'python/Scripts/python.exe', 'gpu_env/Scripts/python.exe'):
        p = root / rel
        if p.is_file():
            return p
    raise RuntimeError('找不到识别环境的 Python 3.12，请重新运行安装识别环境.cmd。')


def check(root, assets, strict_tab=False):
    errors = []
    for rel, expected in assets['homr']['models'].items():
        p = root / rel
        if not p.is_file() or digest(p) != expected:
            errors.append('模型缺失或校验失败：' + rel)
    for rel in ('model_registry.json', 'gpu_runtime_v2/homr_weights_lock.json',
                'teacher_candidates/homr465/repo/homr/main.py',
                'teacher_refinement_v1_20261024/clef_model/detector.json',
                'teacher_refinement_v1_20261024/clef_model/g_core.png',
                'teacher_refinement_v1_20261024/clef_model/eight.png',
                'audio/GeneralUser-GS.sf2', 'audio/fluidsynth/fluidsynth.exe'):
        if not (root / rel).is_file():
            errors.append('缺少文件：' + rel)
    registry = json.loads((root / 'model_registry.json').read_text(encoding='utf-8'))
    model = root / registry['tab_checkpoint']
    tab_ready = model.is_file() and digest(model) == registry['tab_sha256']
    downloads = json.loads((SOURCE / 'engine/runtime-downloads.json').read_text(encoding='utf-8'))
    code_lock = downloads['tab_source']['scripts'] if registry.get('tab_profile') == 'tabbox-official' else downloads['tab_scripts']
    tab_ready = tab_ready and all((root / 'guitar-tab-omr/scripts' / name).is_file() and
        digest(root / 'guitar-tab-omr/scripts' / name) == sha for name, sha in code_lock.items())
    if strict_tab and not tab_ready:
        errors.append('六线谱模型或匹配架构脚本尚未安装。')
    if errors:
        raise RuntimeError('\n'.join(errors))
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(str(root / rel) for rel in (
        'gpu_runtime_v2/pydeps', 'teacher_candidates/homr465/repo',
        'gpu_env/Lib/site-packages', 'smt_pydeps', 'oemer_env/Lib/site-packages'))
    # Queries only; actual inference is still serialized and guarded by gpu_guard.
    program = """import sys
assert sys.version_info[:2] == (3,12), '需要 Python 3.12'
import torch, torchvision, cv2, numpy, PIL, rapidocr, pypdfium2, requests, timm
import onnxruntime as ort
ort.preload_dlls()
from homr import main
assert torch.__version__ == '2.7.1+cu128', torch.__version__
assert ort.__version__ == '1.24.4', ort.__version__
assert torch.cuda.is_available(), 'CUDA 不可用，请检查 NVIDIA 显卡和驱动'
assert 'CUDAExecutionProvider' in ort.get_available_providers(), '缺少 ONNX CUDA 后端'
print('Python、PyTorch、ONNX Runtime 和 CUDA 基础检查通过。')
"""
    subprocess.run([str(interpreter(root)), '-c', program], env=env, check=True)
    subprocess.run([str(root / 'audio/fluidsynth/fluidsynth.exe'), '--version'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('五线谱与采样试听环境检查通过。六线谱：' + ('已安装（' + registry.get('tab_profile', '本地调整版') + '）' if tab_ready else '资源尚未安装。'), flush=True)
    return tab_ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, default=Path(os.environ.get('LOCALAPPDATA', '.')) / 'ScoreFlow/runtime')
    parser.add_argument('--download-cache', type=Path)
    parser.add_argument('--assets-only', action='store_true', help='仅准备资源，不安装依赖、不宣告环境就绪')
    parser.add_argument('--check', action='store_true', help='只检查现有环境，不下载或安装')
    parser.add_argument('--tab-model', type=Path)
    parser.add_argument('--tab-code', type=Path, help='包含 guitar_omr_eval.py 等三个匹配脚本的目录')
    parser.add_argument('--require-tab', action='store_true')
    args = parser.parse_args()
    if bool(args.tab_model) != bool(args.tab_code):
        parser.error('--tab-model 和 --tab-code 必须一起提供，以保证权重与架构匹配。')
    root = args.runtime_root.resolve()
    if root == SOURCE or root.is_relative_to(SOURCE):
        raise ValueError('运行环境请选择源码目录以外的位置，例如 D:\\ScoreFlowRuntime。')
    assets = json.loads((SOURCE / 'engine/model_assets.json').read_text(encoding='utf-8'))
    downloads = json.loads((SOURCE / 'engine/runtime-downloads.json').read_text(encoding='utf-8'))
    if args.check:
        check(root, assets, args.require_tab)
        return
    if os.name != 'nt':
        raise RuntimeError('当前安装脚本仅支持 Windows x64。')
    if not args.assets_only and (sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32):
        raise RuntimeError('请安装 Windows x64 Python 3.12，然后运行：py -3.12 scripts/setup-runtime.py')
    root.mkdir(parents=True, exist_ok=True)
    cache = (args.download_cache or root / '.downloads').resolve()
    print('识别环境安装目录：' + str(root), flush=True)
    if not args.assets_only:
        if not (root / 'python/python.exe').is_file() and not (root / 'python/Scripts/python.exe').is_file():
            subprocess.run([sys.executable, '-m', 'venv', str(root / 'python')], check=True)
        py = str(interpreter(root))
        subprocess.run([py, '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)
        subprocess.run([py, '-m', 'pip', 'install',
            'torch==2.7.1', 'torchvision==0.22.1', '--index-url', 'https://download.pytorch.org/whl/cu128'], check=True)
        subprocess.run([py, '-m', 'pip', 'install',
            '-r', str(SOURCE / 'requirements-runtime.txt')], check=True)
    for name, destination, selection in (
        ('homr_source', root / 'teacher_candidates/homr465/repo',
         lambda p: PurePosixPath(*p.parts[1:]) if len(p.parts) > 1 and
         (p.parts[1] == 'homr' or p.parts[1] in ('LICENSE', 'pyproject.toml', 'README.md')) else None),
        ('fluidsynth', root / 'audio/fluidsynth',
         lambda p: PurePosixPath(*p.parts[2:]) if len(p.parts) > 2 and p.parts[1] == 'bin' else None),
    ):
        asset = downloads[name]
        archive = download(asset['url'], cache / (name + '.zip'), asset['sha256'])
        extract_selected(archive, destination, selection)
    for rel, sha in assets['homr']['models'].items():
        target = root / rel
        download('https://github.com/liebharc/homr/releases/download/onnx_checkpoints/' + target.name, target, sha)
    font = downloads['soundfont']
    download(font['url'], root / 'audio/GeneralUser-GS.sf2', font['sha256'])
    calibration = root / 'teacher_refinement_v1_20261024/clef_model'
    calibration.mkdir(parents=True, exist_ok=True)
    for p in (SOURCE / 'engine/assets/clef_model').iterdir():
        if p.is_file():
            shutil.copy2(p, calibration / p.name)
    for p in (SOURCE / 'licenses').glob('*.txt'):
        shutil.copy2(p, root / 'audio' / p.name)
    registry = dict(assets['registry'])
    if not args.tab_model:
        tab = downloads['tab_model']
        target = root / 'models/tabbox-official.pt'
        download(tab['url'], target, tab['sha256'])
        code = downloads['tab_source']
        archive = download(code['url'], cache / 'tab_source.zip', code['sha256'])
        extract_selected(archive, root / 'guitar-tab-omr/scripts',
            lambda p: PurePosixPath(p.name) if len(p.parts) == 3 and p.parts[1] == 'scripts' and p.name in code['scripts'] else None)
        registry.update(tab_profile='tabbox-official', tab_checkpoint='models/tabbox-official.pt',
            mixed_tab_checkpoint='models/tabbox-official.pt', tab_sha256=tab['sha256'], mixed_tab_sha256=tab['sha256'])
    if args.tab_model:
        if digest(args.tab_model) != assets['registry']['tab_sha256']:
            raise ValueError('六线谱模型与本版登记哈希不同，请获取匹配的调整版，不能替换成原版。')
        target = root / 'models/best.pt'
        target.parent.mkdir(parents=True, exist_ok=True)
        if args.tab_model.resolve() != target.resolve():
            shutil.copy2(args.tab_model, target)
    if args.tab_code:
        for name, sha in downloads['tab_scripts'].items():
            source = args.tab_code / name
            if not source.is_file() or digest(source) != sha:
                raise ValueError('六线谱脚本版本不匹配：' + name)
        target = root / 'guitar-tab-omr/scripts'
        target.mkdir(parents=True, exist_ok=True)
        for name in downloads['tab_scripts']:
            source = args.tab_code / name
            if source.resolve() != (target / name).resolve():
                shutil.copy2(source, target / name)
    write_json(root / 'model_registry.json', registry)
    write_json(root / 'gpu_runtime_v2/homr_weights_lock.json', assets['homr'])
    if args.assets_only:
        print('资源已准备；尚未安装或验证 Python 依赖，未修改应用环境配置。', flush=True)
        return
    check(root, assets, args.require_tab)
    write_json(SOURCE / 'runtime.local.json', {'root': str(root)})
    print('安装完成。双击“启动谱音.cmd”，导入谱面即可识别、试听和保存 MIDI。', flush=True)
    print('默认六线谱使用 Tabbox 公开权重；本地调整版可另行配置，详见 README。', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print('\n安装或检查未完成：' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
