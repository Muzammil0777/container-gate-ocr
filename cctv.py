"""Watch CCTV / RTSP cameras (or a video file / webcam) and log every truck that passes
to Excel: date, time, direction, Saudi number plate (Latin + Arabic), container code,
camera, location and snapshots.

    python cctv.py --config cameras.json
    python cctv.py --source videos/video1.mp4 --direction IN --location "Gate 1" --show
"""
import argparse
import json
import threading
import time
from pathlib import Path

import cv2

from src.gate import ExcelLog, GateTracker
from src.recognizer import Recognizer, draw

DEFAULTS = {
    'excel': 'logs/gate_log_%Y-%m.xlsx', 'snapshots': 'logs/snapshots',
    'fps': 2,                   # OCR passes per second per camera (~0.6 s each on CPU)
    'min_hits': 2, 'window_s': 15, 'cooldown_s': 300, 'accept_unverified': True,
    'motion_threshold': 2.0,    # mean pixel change below which an empty scene is skipped...
    'idle_check_s': 2,          # ...but still checked this often (a truck parked at the barrier)
    'max_side': 1920, 'use_cuda': False,
    'plates': True,             # read Saudi number plates
    'language': 'en',           # Excel headers/values: 'en' or 'ar'
    'gap_s': 5,                 # a visit ends when nothing new was read for this long...
    'max_wait_s': 10,           # ...or this long after the first confirmed read
}


class LatestFrame:
    """Reads a live stream in the background and keeps only the newest frame, so slow OCR
    never makes us fall behind the live feed. Reconnects when the stream drops."""

    def __init__(self, source):
        self.source, self.frame, self.stopped = source, None, False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stopped:
            cap = cv2.VideoCapture(self.source)
            while not self.stopped and cap.isOpened():
                ok, frame = cap.read()
                if not ok:
                    break
                self.frame = frame
            cap.release()
            if not self.stopped:
                print(f"[cctv] lost {_redact(self.source)}, reconnecting in 5 s")
                time.sleep(5)

    def read(self):
        frame, self.frame = self.frame, None
        return frame


def watch(cam, cfg, recognizer, ocr_lock, log, previews, stop):
    name, source = cam['name'], cam['source']
    tracker = GateTracker(cfg['min_hits'], cfg['window_s'], cfg['cooldown_s'], cfg['accept_unverified'],
                          cfg['gap_s'], cfg['max_wait_s'])
    where = (name, cam.get('location', ''), cam.get('direction', ''))
    is_file = isinstance(source, str) and Path(source).is_file()
    if is_file:
        cap = cv2.VideoCapture(source)
        step = max(1, round((cap.get(cv2.CAP_PROP_FPS) or 25) / cfg['fps']))
    else:
        stream = LatestFrame(int(source) if str(source).isdigit() else source)
    print(f"[cctv] {name}: watching {_redact(source)} ({cam.get('direction', '')} @ {cam.get('location', '')})")
    prev, busy, n, last_ocr = None, False, 0, -1e9
    while not stop.is_set():
        t0 = time.time()
        if is_file:
            for _ in range(step):
                ok, frame = cap.read()
            if not ok:
                break
            n += step
            now = n / (cap.get(cv2.CAP_PROP_FPS) or 25)   # video time, so cooldowns behave
        else:
            frame, now = stream.read(), t0
            if frame is None:
                time.sleep(0.05)
                continue
        # Skip OCR on a static, empty scene (but keep reading while a code is being voted on)
        small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
        moving = prev is None or cv2.absdiff(small, prev).mean() > cfg['motion_threshold']
        prev = small
        if moving or busy or now - last_ocr >= cfg['idle_check_s']:
            last_ocr = now
            with ocr_lock:
                out = recognizer(frame, plates=cfg['plates'])
            busy = bool(out['codes'] or out['plates'])
            _log(tracker.update(out['codes'], frame, now, out['plates']), log, *where)
            if previews is not None:
                previews[name] = draw(frame.copy(), out['codes'], out['plates'])
        else:
            _log(tracker.update([], frame, now), log, *where)  # lets a finished visit end
        if not is_file:
            time.sleep(max(0.0, 1 / cfg['fps'] - (time.time() - t0)))
    _log(tracker.flush(), log, *where)
    if not is_file:
        stream.stopped = True
    print(f"[cctv] {name}: stopped")


def _log(events, log, camera, location, direction):
    for e in events:
        row = log.log(e, camera, location, direction)
        print(f"[cctv] {row['date']} {row['time']}  {row['direction']:<4} plate {row['plate'] or '-':<9} "
              f"container {row['container'] or '-':<14}  {camera} / {location}")


def _redact(source):
    """Hide the password in rtsp://user:pass@host URLs when printing."""
    s = str(source)
    if '@' in s and '://' in s:
        scheme, rest = s.split('://', 1)
        return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', help='JSON file with settings and a "cameras" list (see cameras.example.json)')
    ap.add_argument('--source', help='single camera: RTSP URL, video file, or webcam index (0)')
    ap.add_argument('--name', default='Camera 1')
    ap.add_argument('--direction', default='IN', help='IN or OUT for this camera')
    ap.add_argument('--location', default='')
    ap.add_argument('--show', action='store_true', help='show live preview windows (q to quit)')
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    if args.config:
        cfg.update(json.loads(Path(args.config).read_text(encoding='utf-8')))
    elif args.source:
        cfg['cameras'] = [{'name': args.name, 'source': args.source,
                           'direction': args.direction, 'location': args.location}]
    else:
        ap.error('give --config or --source')

    recognizer, ocr_lock = Recognizer(cfg['max_side'], cfg['use_cuda']), threading.Lock()
    log = ExcelLog(cfg['excel'], cfg['snapshots'], cfg['language'])
    previews, stop = ({} if args.show else None), threading.Event()
    threads = [threading.Thread(target=watch, args=(cam, cfg, recognizer, ocr_lock, log, previews, stop),
                                daemon=True) for cam in cfg['cameras']]
    for t in threads:
        t.start()
    print(f"[cctv] logging to {cfg['excel']}  (Ctrl+C to stop)")
    try:
        while any(t.is_alive() for t in threads):
            if previews is not None:   # OpenCV windows must be driven from the main thread
                for name, img in list(previews.items()):
                    cv2.imshow(name, img)
                if cv2.waitKey(50) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.5)
            log.flush()   # retry rows queued while the workbook was open in Excel
    except KeyboardInterrupt:
        pass
    stop.set()
    for t in threads:
        t.join(timeout=5)
    log.flush()
    if log.pending:
        print(f"[cctv] WARNING: {len(log.pending)} row(s) not written, the workbook is still open:")
        for _, row in log.pending:
            print('   ', row)
    if args.show:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
