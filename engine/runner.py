"""Headless JSON-lines bridge. Holds a Windows Job Object for the entire job."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['recognize', '_worker'])
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--meter')
    parser.add_argument('--mode', choices=['auto', 'staff', 'tab'], default='auto')
    args = parser.parse_args()
    if args.action == '_worker':
        if sys.stdin.readline().strip() != 'SCOREFLOW_START':
            raise RuntimeError('Worker launch gate was not released.')
        from runtime_paths import activate_cpu
        activate_cpu()
        from pipeline import recognize
        meter = tuple(map(int, args.meter.split('/'))) if args.meter else None
        recognize(args.image, args.output, meter=meter, mode=args.mode)
        print(json.dumps({'stage':'saved','message':'MIDI 已自动保存，可直接试听或另存文件。'}, ensure_ascii=False), flush=True)
        return
    from gpu_guard import ProcessJob
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), '_worker', '--image', str(args.image), '--output', str(args.output), '--mode', args.mode]
    if args.meter: command += ['--meter', args.meter]
    cancelled = threading.Event()
    def control():
        for line in sys.stdin:
            if line.strip() == 'CANCEL': cancelled.set(); break
    threading.Thread(target=control, daemon=True).start()
    with ProcessJob() as job:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=None, stderr=None,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            job.attach(child)
            child.stdin.write(b'SCOREFLOW_START\n'); child.stdin.flush(); child.stdin.close()
            while child.poll() is None and not cancelled.is_set(): time.sleep(.1)
            code = child.poll()
        finally:
            if child.stdin and not child.stdin.closed: child.stdin.close()
    child.wait(timeout=10)
    if cancelled.is_set():
        # Controlled cancellation occurs after closing the process-tree job.
        # Only clear an interrupted RUNNING record; retain genuine fault latches.
        from gpu_guard import STATE, GPULock, snapshot, check_health, write_json, stamp
        with GPULock():
            state = STATE / 'state.json'
            if state.is_file():
                record = json.loads(state.read_text(encoding='utf-8'))
                if record.get('status') == 'running':
                    health = snapshot(); check_health(health, starting=True)
                    record.update(status='ready', finished=stamp(), reason='user cancelled', health_after=health)
                    write_json(state, record)
        print('识别已取消', file=sys.stderr)
        raise SystemExit(130)
    if code: raise SystemExit(code)

if __name__ == '__main__':
    try: main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
