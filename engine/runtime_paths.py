"""Relocatable model assets and pinned ABI-compatible Python dependencies."""
import os
from pathlib import Path
import sys

CODE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get('SCOREFLOW_RUNTIME_ROOT', str(CODE.parent / 'runtime'))).resolve()

def gpu_python():
    for relative in ('python/python.exe', 'python/Scripts/python.exe', 'gpu_env/Scripts/python.exe'):
        candidate = RUNTIME / relative
        if candidate.is_file():
            return candidate
    raise FileNotFoundError('找不到 Python 3.12，请先运行安装识别环境.cmd。')

def activate_cpu():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('The pinned recognition runtime requires Python 3.12.')
    # Preserve the established dependency priority and avoid the old Qt UI.
    locations = [RUNTIME / 'gpu_runtime_v2/pydeps', RUNTIME / 'teacher_candidates/homr465/repo',
                 RUNTIME / 'teacher_candidates/homr465/pydeps', RUNTIME / 'gpu_env/Lib/site-packages',
                 RUNTIME / 'smt_pydeps', RUNTIME / 'oemer_env/Lib/site-packages']
    for p in reversed(locations):
        while str(p) in sys.path: sys.path.remove(str(p))
        sys.path.insert(0, str(p))

def activate_gpu():
    activate_cpu()
    import onnxruntime
    if onnxruntime.__version__ != '1.24.4':
        raise RuntimeError('需要 onnxruntime-gpu 1.24.4，请按安装指引配置识别环境。')
