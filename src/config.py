"""Site settings (cameras.json), the detection service and saving corrections: shared by
the app and the API. The gate service (cctv.py) reads cameras.json and applies changes
within a second; it reports back through logs/live/status.json."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from cctv import DEFAULTS
from src.camera import open_capture
from src.gate import GateLog

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'cameras.json'
LIVE = ROOT / DEFAULTS['live_dir']


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    tmp = CONFIG.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, CONFIG)


def service_status():
    """(service running?, {camera name: status}) from the status file the service writes."""
    try:
        s = json.loads((LIVE / 'status.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False, {}
    return time.time() - s.get('updated', 0) < 10, s.get('cameras', {})


def start_service():
    """Start the gate service in the background (no window); its output goes to logs/service.log."""
    if not CONFIG.exists():
        save_config({})
    (ROOT / 'logs').mkdir(exist_ok=True)
    log = open(ROOT / 'logs' / 'service.log', 'a', encoding='utf-8')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen([sys.executable, str(ROOT / 'cctv.py'), '--config', str(CONFIG)], cwd=ROOT,
                     stdout=log, stderr=subprocess.STDOUT, creationflags=flags)


def grab_frame(source):
    """One fresh frame from a camera / stream URL / webcam index, or None."""
    cap = open_capture(int(source) if str(source).isdigit() else source)
    frame = None
    for _ in range(5):  # skip stale buffered frames
        ok, f = cap.read()
        frame = f if ok else frame
    cap.release()
    return frame


def save_fix(store, row, fix):
    """Save a person's correction of a stored row (fields from store.parse_fix): update the
    database, rewrite that day's and month's Excel files, and keep a before/after record in
    logs/corrections.jsonl for improving accuracy later."""
    store.correct(row['id'], **fix)
    gl = GateLog(store, DEFAULTS['snapshots'], ROOT / DEFAULTS['excel_dir'], load_config().get('language', 'en'))
    gl.changed(row['date'])
    gl.flush()
    (ROOT / 'logs').mkdir(exist_ok=True)
    with open(ROOT / 'logs' / 'corrections.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps({'id': row['id'], 'before': {k: row.get(k) for k in fix}, 'after': fix,
                            'snapshot': row.get('snapshot')}, ensure_ascii=False) + '\n')
