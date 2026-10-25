"""Supervise explicit CUDA runs on this Windows workstation, before importing CUDA.

This cannot preempt a bad kernel before Windows TDR. Limits reduce exposure;
they do not repair drivers/hardware or certify that a workload is stable.
"""
import argparse
import csv
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

B = Path(__file__).resolve().parent
STATE = Path(os.environ.get('SCOREFLOW_STATE_ROOT', str(B / 'gpu_runs')))
STATE.mkdir(parents=True, exist_ok=True)
BUDGET_MIB = 3072
RESERVE_MIB = 2048
MAX_TEMP_C = 75
TIMEOUT_SECONDS = 360
FAULT_EXIT = 86
_supervised = False


class GPURefused(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


class GPULock:
    """OS releases this lock on process exit, including abnormal exit."""
    def __enter__(self):
        if os.name != 'nt':
            raise GPURefused('This supervisor requires Windows Job Objects.')
        import msvcrt
        STATE.mkdir(exist_ok=True)
        self.file = (STATE / 'device.lock').open('a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.file.close()
            raise GPURefused('Another guarded GPU task is running; no parallel launch.') from exc
        return self

    def __exit__(self, *args):
        import msvcrt
        self.file.seek(0)
        msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        self.file.close()


class ProcessJob:
    """Kill worker AND venv launcher descendants if supervisor exits/times out."""
    def __enter__(self):
        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                        ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD),
                        ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t),
                        ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t),
                        ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in
                        ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                         'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO),
                        ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t),
                        ('PeakJobMemoryUsed', ctypes.c_size_t)]
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.k.CreateJobObjectW.restype = wintypes.HANDLE
        self.k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                  ctypes.c_void_p, wintypes.DWORD]
        self.k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.k.CloseHandle(self.handle)
            raise error
        return self

    def attach(self, process):
        # Popen retains this Windows process handle; child waits for our stdin gate.
        if not self.k.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def __exit__(self, *args):
        self.k.CloseHandle(self.handle)


def snapshot():
    exe = shutil.which('nvidia-smi')
    if not exe:
        raise GPURefused('nvidia-smi not found; GPU health cannot be checked.')
    fields = 'uuid,name,driver_version,memory.total,memory.free,temperature.gpu,utilization.gpu,power.draw,fan.speed'
    try:
        cp = subprocess.run([exe, '-i', '0', '--query-gpu=' + fields,
                             '--format=csv,noheader,nounits'], capture_output=True,
                            text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
        if cp.returncode:
            raise GPURefused('GPU health query failed: ' + (cp.stderr + cp.stdout)[-800:])
        row = next(csv.reader(cp.stdout.splitlines(), skipinitialspace=True))
        values = dict(zip(fields.split(','), row))
        for key in ('memory.total', 'memory.free', 'temperature.gpu'):
            values[key] = float(values[key])
            if not math.isfinite(values[key]):
                raise ValueError('non-finite telemetry')
        values['at'] = stamp()
        return values
    except (OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired) as exc:
        raise GPURefused('GPU telemetry unavailable: ' + str(exc)) from exc


def check_health(data, starting=False):
    if data['temperature.gpu'] >= MAX_TEMP_C:
        raise GPURefused(f'GPU temperature reached stop threshold {MAX_TEMP_C} C.')
    needed = RESERVE_MIB + BUDGET_MIB + 512 if starting else RESERVE_MIB
    if data['memory.free'] < needed:
        raise GPURefused(f'GPU free memory {data["memory.free"]} MiB below {needed} MiB threshold.')


_next_cooling_check = 0.0
def cool_between_patches(check_interval=1.0,pause_c=68,resume_c=65):
    """Pause host submission before the hard limit; use earlier checks for pages."""
    global _next_cooling_check
    if not _supervised:raise GPURefused('Cooling requires the GPU supervisor.')
    if time.monotonic() < _next_cooling_check:return
    data=snapshot();check_health(data)
    if data['temperature.gpu']>=pause_c:
        print(f'Cooling between GPU patches until <={resume_c} C',flush=True)
        deadline=time.monotonic()+60
        while data['temperature.gpu']>resume_c:
            if time.monotonic()>deadline:raise GPURefused('GPU did not cool within 60 seconds.')
            time.sleep(.5)
            data=snapshot();check_health(data)
    _next_cooling_check=time.monotonic()+check_interval


def supervise(argv):
    with GPULock():
        state_path = STATE / 'state.json'
        if state_path.exists():
            previous = json.loads(state_path.read_text(encoding='utf-8'))
            if previous.get('status') != 'ready':
                raise GPURefused('Previous GPU run failed or was interrupted. Inspect gpu_runs; '
                                 'after recovery use: python gpu_guard.py acknowledge')
        health = snapshot()
        check_health(health, starting=True)
        run_dir = STATE / (datetime.now().strftime('%Y%m%d_%H%M%S_') + secrets.token_hex(3))
        run_dir.mkdir()
        record = {'status': 'running', 'started': stamp(), 'command': argv,
                  'log_dir': str(run_dir), 'health_before': health,
                  'allocator_budget_mib': BUDGET_MIB, 'reserve_mib': RESERVE_MIB,
                  'max_temp_c': MAX_TEMP_C, 'timeout_seconds': TIMEOUT_SECONDS}
        write_json(state_path, record)  # Remains "running" if supervisor is killed.
        env = os.environ.copy()
        token = secrets.token_hex(24)
        env.update(_OMR_GPU_CHILD_TOKEN=token, OMR_GPU_RUN_DIR=str(run_dir), CUDA_VISIBLE_DEVICES=health['uuid'],
                   CUDA_DEVICE_ORDER='PCI_BUS_ID', PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8',
                   PYTORCH_CUDA_ALLOC_CONF='backend:native,max_split_size_mb:128')
        log_path = run_dir / 'worker.log'
        print('Guarded CUDA run; logs: ' + str(run_dir), flush=True)
        process = None
        reason = None
        code = FAULT_EXIT
        try:
            with ProcessJob() as job, log_path.open('wb') as log:
                process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=log,
                                           stderr=subprocess.STDOUT, env=env,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    job.attach(process)
                    process.stdin.write((token + '\n').encode('ascii'))
                    process.stdin.close()
                    started = time.monotonic()
                    next_poll = 0.0
                    offset = 0
                    carry = ''
                    with log_path.open('rb') as reader, (run_dir / 'telemetry.jsonl').open('w', encoding='utf-8') as telemetry:
                        while True:
                            now = time.monotonic()
                            if now - started > TIMEOUT_SECONDS:
                                raise GPURefused('GPU worker exceeded wall-clock timeout; stopping process tree.')
                            reader.seek(offset)
                            chunk = reader.read()
                            offset += len(chunk)
                            # Windows C++ ORT diagnostics may contain UTF-16 NULs.
                            text = (carry + chunk.decode('utf-8', errors='replace')).replace('\x00','').lower()
                            carry = text[-512:]
                            for signal in ('cuda failure', 'cuda error:', 'cudaerror', 'cudnn_status_',
                                           'gpu is lost', 'device lost', 'out of memory',
                                           'ep error', 'falling back to', 'may be extremely slow',
                                           'smaller than requested bytes'):
                                if signal in text:
                                    raise GPURefused('GPU worker reported: ' + signal)
                            code = process.poll()
                            if code is not None:
                                if code:
                                    raise GPURefused(f'GPU worker failed (exit {code}); no retry or CPU fallback.')
                                break
                            if now >= next_poll:
                                data = snapshot()
                                telemetry.write(json.dumps(data) + '\n')
                                telemetry.flush()
                                check_health(data)
                                next_poll = time.monotonic() + 1
                            time.sleep(.1)
                finally:
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
            # Closing the job also removes any unexpected surviving descendants.
            process.wait(timeout=10)
            record['health_after'] = snapshot()
            check_health(record['health_after'])
        except BaseException as exc:
            reason = f'{type(exc).__name__}: {exc}'
            # Job close has already killed attached descendants. If attach failed,
            # closing stdin prevents the waiting child from ever importing CUDA.
            if process is not None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        record.update(status='fault' if reason else 'ready', finished=stamp(),
                      returncode=code, reason=reason)
        write_json(run_dir / 'run.json', record)
        write_json(state_path, record)
        if reason:
            print(reason + '\nGPU queue stopped. See ' + str(log_path), file=sys.stderr)
            return FAULT_EXIT
        return 0


def bootstrap(device):
    """Call once at script entry, before torch/ORT imports and argument mutation."""
    global _supervised
    if device == 'cpu':
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
        return
    if device != 'cuda':
        raise ValueError('Device must be explicitly cpu or cuda; auto fallback is disabled.')
    token = os.environ.pop('_OMR_GPU_CHILD_TOKEN', None)
    if token:
        if sys.stdin.buffer.readline(128).strip() != token.encode('ascii'):
            raise GPURefused('GPU supervisor did not authorize worker startup.')
        _supervised = True
        return
    try:
        code = supervise([sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]])
    except (GPURefused, OSError, ValueError) as exc:
        print('GPU launch refused: ' + str(exc), file=sys.stderr)
        code = FAULT_EXIT
    raise SystemExit(code)


def configure_torch(torch):
    if not _supervised:
        raise GPURefused('CUDA configuration requires the supervisor.')
    if not torch.cuda.is_available():
        raise GPURefused('Explicit CUDA requested but unavailable; CPU fallback disabled.')
    torch.cuda.set_device(0)
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(BUDGET_MIB * 1024**2 / total, .5), 0)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def cuda_options():
    if not _supervised:
        raise GPURefused('CUDA session requires the supervisor.')
    return {'device_id': 0, 'gpu_mem_limit': BUDGET_MIB * 1024**2,
            'arena_extend_strategy': 'kSameAsRequested',
            'cudnn_conv_algo_search': 'HEURISTIC', 'cudnn_conv_use_max_workspace': '0',
            'do_copy_in_default_stream': '1', 'use_tf32': '0'}


def require_cuda_session(session):
    session.disable_fallback()  # ORT otherwise retries EPFail using CPU.
    if not session.get_providers() or session.get_providers()[0] != 'CUDAExecutionProvider':
        raise GPURefused('CUDA provider initialization failed; CPU fallback disabled.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'acknowledge'])
    args = parser.parse_args()
    with GPULock():
        data = snapshot()
        path = STATE / 'state.json'
        if args.action == 'acknowledge':
            check_health(data, starting=True)
            # Keep the incident record; acknowledging is not a GPU stability test.
            if path.exists():
                archive = STATE / ('acknowledged_' + datetime.now().strftime('%Y%m%d_%H%M%S_') + secrets.token_hex(3) + '.json')
                shutil.copyfile(path, archive)
            write_json(path, {'status': 'ready', 'acknowledged_at': stamp(), 'health': data})
        print(json.dumps({'health': data, 'state': json.loads(path.read_text(encoding='utf-8')) if path.exists() else None}, indent=2))


if __name__ == '__main__':
    main()
