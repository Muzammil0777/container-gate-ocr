"""Gate detection service: watches CCTV cameras (Hikvision NVR, any RTSP camera, a video file
or a webcam) and logs every truck that passes: date, time, direction, Saudi number plate
(Latin + Arabic), container code, camera, location and snapshots, into the database and the
daily/monthly Excel files.

    python cctv.py --scan --ip 192.168.1.64 --user admin --password "..."   # find cameras
    python cctv.py --config cameras.json                                     # run the gate service
    python cctv.py --source videos/video1.mp4 --direction IN --location "Gate 1"

With --config it keeps running and re-reads the file every few seconds, so cameras added,
changed or stopped in the app take effect without a restart.
"""
import argparse
import getpass
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from src.camera import camera_source, hikvision_url, open_capture, port_open, redact

import cv2

from src import license
from src.gate import GateLog, LaneTracker
from src.lanes import lanes
from src.recognizer import Recognizer, draw
from src.scanner import Scanner
from src.store import Store

DEFAULTS = {
    'db': 'logs/gate.db', 'excel_dir': 'logs/excel', 'snapshots': 'logs/snapshots',
    'live_dir': 'logs/live',    # latest annotated frame per camera + status.json, for the app
    'fps': 4,                   # looks per second per camera, at most (full scans are slower)
    'min_hits': 2, 'window_s': 15, 'cooldown_s': 300, 'accept_unverified': True,
    'motion_threshold': 2.0,    # mean pixel change below which an empty scene is skipped...
    'idle_check_s': 2,          # ...but still checked this often (a truck parked at the barrier)
    'max_side': 1920, 'use_cuda': False,
    'plates': True,             # read Saudi number plates
    'language': 'en',           # Excel headers/values: 'en' or 'ar'
    'gap_s': 5,                 # a visit ends when nothing new was read for this long...
    'max_wait_s': 10,           # ...or this long after the first confirmed read
}
STATUS_EVERY_S = 2
LICENSE_EVERY_S = 30  # a renewed key restarts detection within this time


class LatestFrame:
    """Reads a live stream in the background and keeps only the newest frame, so slow OCR
    never makes us fall behind the live feed. Reconnects when the stream drops."""

    def __init__(self, source, name):
        self.source, self.name, self.frame, self.stopped = source, name, None, False
        self.last_frame_at = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stopped:
            cap = open_capture(self.source)
            if cap.isOpened():
                print(f"[cctv] {self.name}: connected, {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                      f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps")
            while not self.stopped and cap.isOpened():
                ok, frame = cap.read()
                if not ok:
                    break
                self.frame, self.last_frame_at = frame, time.time()
            cap.release()
            if not self.stopped:
                print(f"[cctv] {self.name}: no video from {redact(self.source)}, retrying in 5 s "
                      f"(run with --scan to check the connection)")
                time.sleep(5)

    def read(self):
        frame, self.frame = self.frame, None
        return frame


class Lane:
    """A gate lane while it runs: its cameras' threads feed one LaneTracker, which logs one row
    per truck with every camera's photo. A camera without a lane is a lane of its own."""

    def __init__(self, ln, cfg, log):
        self.cams = ln['cameras']
        self.tracker = LaneTracker([(c['name'], c['role']) for c in self.cams], cfg['min_hits'], cfg['window_s'],
                                   cfg['cooldown_s'], cfg['accept_unverified'], cfg['gap_s'], cfg['max_wait_s'])
        self.log, self.location, self.direction = log, ln.get('location', ''), ln.get('direction', '')
        # a lane from the settings' "lanes" (its row says so); a camera on its own logs rows as before
        self.name = ln['name'] if self.cams[0].get('lane') == ln['name'] else None
        self.lock, self.running = threading.Lock(), len(self.cams)

    def update(self, camera, codes, frame, now, plates=()):
        self._log(self.tracker.update(camera, codes, frame, now, plates))

    def done(self):
        """A camera thread ended; the last one writes the visit in progress."""
        with self.lock:
            self.running -= 1
            last = self.running == 0
        if last:
            self._log(self.tracker.flush())

    def _log(self, events):
        for e in events:
            camera = (e['code'] or e['plate'])['cam']   # the camera of the row's main photo
            row = self.log.log(e, camera, self.location, self.direction, lane=self.name)
            note = {'merged': '  (added to the earlier row)', 'duplicate': '  (duplicate, not added)'}.get(row['status'], '')
            print(f"[cctv] {row['date']} {row['time']}  {row['direction'] or '':<4} plate {row['plate'] or '-':<9} "
                  f"container {row['container'] or '-':<14}  {camera} / {self.location}{note}")


def one_lane(cam):
    """A camera on its own (a --source run, or tests) as the lane lanes() would make of it."""
    return {'name': cam['name'], 'direction': cam.get('direction', ''), 'location': cam.get('location', ''),
            'cameras': [{**cam, 'role': 'both'}], 'cams_expected': 1}


def watch(cam, cfg, recognizer, ocr_lock, lane, previews, stop, status=None):
    """Run one camera of `lane` until `stop` is set (or a video file ends). `status` (a dict) is
    kept up to date with last_frame_at / last_ocr_ms / connected for the app."""
    try:
        _watch(cam, cfg, recognizer, ocr_lock, lane, previews, stop, {} if status is None else status)
    finally:
        lane.done()


def _watch(cam, cfg, recognizer, ocr_lock, lane, previews, stop, status):
    name = cam['name']
    source = camera_source(cam, cfg.get('nvr'))
    scanner = Scanner(recognizer)
    roi = cam.get('roi')  # [left, top, right, bottom] as fractions of the frame; None = whole frame
    is_file = isinstance(source, str) and Path(source).is_file()
    if is_file:
        cap = cv2.VideoCapture(source)
        step = max(1, round((cap.get(cv2.CAP_PROP_FPS) or 25) / cfg['fps']))
    else:
        stream = LatestFrame(source, name)
    print(f"[cctv] {name}: watching {redact(source)} ({lane.direction} @ {lane.location})")
    live = Path(cfg['live_dir']) / f"{_safe(name)}.jpg"
    live.parent.mkdir(parents=True, exist_ok=True)
    status.update(started_at=time.time(), last_frame_at=0.0, last_ocr_ms=None)
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
            status['last_frame_at'] = t0
        else:
            frame, now = stream.read(), t0
            status['last_frame_at'] = stream.last_frame_at
            if frame is None:
                time.sleep(0.05)
                continue
        if roi:
            H, W = frame.shape[:2]
            frame = frame[int(roi[1] * H):int(roi[3] * H), int(roi[0] * W):int(roi[2] * W)]
        # Skip OCR on a static, empty scene (but keep reading while a code is being voted on)
        small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
        moving = prev is None or cv2.absdiff(small, prev).mean() > cfg['motion_threshold']
        prev = small
        if moving or busy or now - last_ocr >= cfg['idle_check_s']:
            last_ocr = now
            with ocr_lock:
                # live: no zoom pass (reads are combined across frames instead); a reading area is
                # already a close-up, so it is searched at 1600 px (about 30% faster)
                out = scanner(frame, now, plates=cfg['plates'], zoom=False,
                              max_side=cam.get('max_side', 1600 if roi else cfg['max_side']))
            status['last_ocr_ms'] = out['ms']
            busy = bool(out['codes'] or out['plates'])
            lane.update(name, out['codes'], frame, now, out['plates'])
            shown = draw(frame.copy(), out['codes'], out['plates'])
            _write_live(live, shown, f"{name}  {datetime.now():%H:%M:%S}  OCR {out['ms']} ms")
            if previews is not None:
                previews[name] = shown
        else:
            lane.update(name, [], frame, now)  # lets a finished visit end
        if not is_file:
            time.sleep(max(0.0, 1 / cfg['fps'] - (time.time() - t0)))
    if not is_file:
        stream.stopped = True
    print(f"[cctv] {name}: stopped")


def _write_live(path, img, caption):
    """Save the latest annotated frame for the app's Live tab (atomic, so the app never
    reads a half-written file)."""
    scale = min(1.0, 1280 / img.shape[1])
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img
    cv2.putText(img, caption, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
    cv2.putText(img, caption, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if ok:
        tmp = path.with_suffix('.tmp')
        tmp.write_bytes(buf.tobytes())
        os.replace(tmp, path)


def _safe(name):
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)


class LiveManager:
    """Runs lanes (see src/lanes.py), each camera in a background thread: start/stop lanes
    while the process keeps running. Used by the gate service (driven by cameras.json) and by tests."""

    def __init__(self, cfg=None):
        self.cfg = {**DEFAULTS, **(cfg or {})}
        # ponytail: keyed by name, so a lane and a lone camera with the same name clash
        self.lanes = {}   # lane name -> (lane entry, effective config, {camera name: (thread, stop event)})
        self.status = {}  # camera name -> live status dict (see watch)
        self.ocr_lock, self.recognizer, self.logs = threading.Lock(), None, {}
        self.store = Store(self.cfg['db'])
        threading.Thread(target=self._flusher, daemon=True).start()

    def log_for(self, language):
        """One GateLog per Excel language, all sharing the same database."""
        if language not in self.logs:
            self.logs[language] = GateLog(self.store, self.cfg['snapshots'], self.cfg['excel_dir'],
                                          language, self.cfg['cooldown_s'])
        return self.logs[language]

    def start(self, cam, nvr=None, language=None):
        """Start (or restart) one camera on its own. Raises ValueError if its connection details are incomplete."""
        self.start_lane(one_lane(cam), nvr, language)

    def start_lane(self, ln, nvr=None, language=None):
        """Start (or restart) a lane's cameras. Raises ValueError, starting none, if one's
        connection details are incomplete."""
        cfg = {**self.cfg, 'nvr': nvr or self.cfg.get('nvr'), 'language': language or self.cfg['language']}
        for cam in ln['cameras']:
            camera_source(cam, cfg['nvr'])
        self.stop(ln['name'])
        if self.recognizer is None:
            self.recognizer = Recognizer(cfg['max_side'], cfg['use_cuda'], vertical_every=3)
        lane, threads = Lane(ln, cfg, self.log_for(cfg['language'])), {}
        for cam in ln['cameras']:
            stop, status = threading.Event(), self.status.setdefault(cam['name'], {})
            threads[cam['name']] = (threading.Thread(target=watch, daemon=True, args=(
                cam, cfg, self.recognizer, self.ocr_lock, lane, None, stop, status)), stop)
        self.lanes[ln['name']] = (ln, cfg, threads)
        for th, _ in threads.values():
            th.start()

    def stop(self, name):
        """Stop a lane (a camera on its own: the camera's name); its visit in progress is logged."""
        _, _, threads = self.lanes.pop(name, (None, None, {}))
        for _, stop in threads.values():
            stop.set()
        for cam, (th, _) in threads.items():
            th.join(timeout=10)
            self.status.pop(cam, None)
            (Path(self.cfg['live_dir']) / f"{_safe(cam)}.jpg").unlink(missing_ok=True)

    def cameras(self):
        """(camera entry, its lane entry, thread) for every camera started."""
        return [(cam, ln, threads[cam['name']][0]) for ln, _, threads in self.lanes.values() for cam in ln['cameras']]

    def running(self):
        return {cam['name']: cam for cam, _, th in self.cameras() if th.is_alive()}

    def flush(self):
        for log in list(self.logs.values()):
            log.flush()

    def _flusher(self):
        while True:  # keep the Excel files current, and retry ones that were open in Excel
            time.sleep(5)
            self.flush()


def licensed(store):
    """Whether the license lets the cameras be read (trial, active, ending soon or grace days)."""
    return license.detection_allowed(license.check(store)['state'])


def follow_license(manager, was):
    """Stop every lane once the license has run out. Returns whether detection is allowed now;
    `was` is the last answer (None at start)."""
    allowed = licensed(manager.store)
    if not allowed:
        for name in list(manager.lanes):
            manager.stop(name)
        if was is not False:
            print('[cctv] The license has ended, so the cameras are not being read. Records and Excel files still work.')
    return allowed


def serve(config_path):
    """The gate service: run the cameras listed in config_path (skipping "enabled": false),
    follow changes to the file, and publish status for the app until Ctrl+C."""
    path = Path(config_path)
    cfg = {**DEFAULTS, **_read_json(path)}
    status_file = Path(cfg['live_dir']) / 'status.json'
    other = _read_json(status_file)
    if other and other.get('pid') != os.getpid() and time.time() - other.get('updated', 0) < 3 * STATUS_EVERY_S:
        print(f"[cctv] The gate service is already running (process {other.get('pid')}); not starting a second copy.")
        return
    manager, mtime, next_status, next_license, allowed = LiveManager(cfg), None, 0, 0, None
    print(f"[cctv] gate service running, following {path.resolve()}  (Ctrl+C to stop)")
    try:
        while True:
            if time.time() >= next_license:
                next_license = time.time() + LICENSE_EVERY_S
                was, allowed = allowed, follow_license(manager, allowed)
                if allowed and was is False:  # a new key: start the cameras again
                    mtime = None
            m = path.stat().st_mtime if path.exists() else None
            if allowed and m != mtime:  # (re)load the lanes; only the ones that changed restart
                mtime, new = m, {**DEFAULTS, **_read_json(path)}
                reload(manager, new)
            if time.time() >= next_status:
                next_status = time.time() + STATUS_EVERY_S
                _write_json(status_file, {'pid': os.getpid(), 'updated': time.time(), 'cameras': {
                    cam['name']: {**manager.status.get(cam['name'], {}), 'alive': th.is_alive(),
                                  'direction': ln['direction'], 'location': ln['location'],
                                  'channel': cam.get('channel'), 'lane': cam.get('lane'), 'role': cam['role']}
                    for cam, ln, th in manager.cameras()}})
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    for name in list(manager.lanes):
        manager.stop(name)
    manager.flush()
    status_file.unlink(missing_ok=True)
    print('[cctv] gate service stopped')


def reload(manager, cfg):
    """Run the lanes of cfg (settings with defaults): stop the lanes that changed or went,
    start the new ones; the others keep running."""
    wanted = {ln['name']: ln for ln in lanes(cfg)}
    for name in list(manager.lanes):
        ln, run_cfg, _ = manager.lanes[name]
        if wanted.get(name) != ln or run_cfg.get('nvr') != cfg.get('nvr') or run_cfg['language'] != cfg['language']:
            manager.stop(name)
    for name, ln in wanted.items():
        if name not in manager.lanes:
            try:
                manager.start_lane(ln, cfg.get('nvr'), cfg['language'])
            except ValueError as e:
                print(f"[cctv] {e}")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def scan(nvr, channels, out_dir='logs/scan'):
    """Check the connection to a Hikvision NVR and save one snapshot per working channel."""
    ip, port = nvr['ip'], nvr.get('port', 554)
    print(f"[scan] 1/2 Can this computer reach {ip}?")
    if not port_open(ip, port):
        if port_open(ip, 80) or port_open(ip, 443):
            print(f"  The NVR answers, but its video port {port} is closed. On the NVR: Configuration >"
                  f" Network > Advanced Settings (or Port): check the RTSP port number and use that as 'port'.")
        else:
            print(f"  No answer from {ip}. Check that:\n"
                  f"   - the IP address is right (on the NVR screen: Menu > Configuration > Network)\n"
                  f"   - this laptop is on the same network (plugged into the same switch / Wi-Fi as the NVR)\n"
                  f"   - your laptop has an address in the same range, e.g. 192.168.1.x for an NVR at 192.168.1.64")
        return []
    print(f"  Yes, {ip}:{port} is reachable.")
    print(f"[scan] 2/2 Trying channels 1-{channels} (a few seconds each)...")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    found = []
    for ch in range(1, channels + 1):
        cap = open_capture(hikvision_url(ip, nvr['user'], nvr['password'], ch, 'main', port), 5000)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        cap.release()
        if ok:
            snap = out / f"channel_{ch}.jpg"
            cv2.imwrite(str(snap), frame)
            found.append(ch)
            print(f"  channel {ch:>2}: OK  {frame.shape[1]}x{frame.shape[0]}  -> {snap}")
    if not found:
        print("  No channel answered. The network is fine, so check:\n"
              "   - the username and password (case-sensitive; the NVR may lock the account after\n"
              "     several wrong tries, wait 30 minutes or ask the site admin)\n"
              "   - that this user is allowed live view (NVR: Configuration > User Management)\n"
              "   - NVR: Configuration > Network > Advanced > Integration Protocol: allow RTSP if it's off")
    else:
        print(f"\n[scan] Open the snapshots in {out.resolve()} and note which channel looks at the gate.\n"
              f"Then add those channels in the app's Cameras tab.")
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', help='JSON file with settings, an "nvr" block and a "cameras" list '
                                     '(see cameras.example.json); runs as the gate service')
    ap.add_argument('--source', help='single camera: RTSP URL, video file, or webcam index (0)')
    ap.add_argument('--ip', help='Hikvision NVR/camera IP address')
    ap.add_argument('--user', default='admin', help='NVR username (default admin)')
    ap.add_argument('--password', help='NVR password (prefer putting it in cameras.json)')
    ap.add_argument('--channel', type=int, help='NVR channel number of the gate camera')
    ap.add_argument('--scan', action='store_true', help='check the NVR connection and list working channels')
    ap.add_argument('--channels', type=int, default=32, help='how many channels --scan tries (default 32)')
    ap.add_argument('--name', default='Camera 1')
    ap.add_argument('--direction', default='IN', help='IN or OUT for this camera')
    ap.add_argument('--location', default='')
    ap.add_argument('--show', action='store_true', help='show live preview windows (q to quit)')
    args = ap.parse_args()

    cfg = {**DEFAULTS, **(_read_json(args.config) if args.config else {})}
    if args.ip:
        cfg['nvr'] = {'ip': args.ip, 'user': args.user, 'password': args.password or '',
                      **{k: v for k, v in cfg.get('nvr', {}).items() if k == 'port'}}
    if args.scan:
        if 'nvr' not in cfg:  # ask (password hidden) rather than making people type it in a command
            ip = input('NVR IP address (e.g. 192.168.1.64): ').strip()
            user = input('Username [admin]: ').strip() or 'admin'
            cfg['nvr'] = {'ip': ip, 'user': user, 'password': getpass.getpass('Password (hidden): ')}
        scan(cfg['nvr'], args.channels)
        return
    if args.config and not (args.source or args.channel):
        serve(args.config)
        return
    if not (args.source or args.channel):
        ap.error('give --config, --source, or --ip/--password/--channel')
    cam = {'source': args.source} if args.source else {'channel': args.channel}
    cam.update(name=args.name, direction=args.direction, location=args.location)
    camera_source(cam, cfg.get('nvr'))  # fail now on a missing ip/password, not in a thread
    if not licensed(Store(cfg['db'])):
        print('[cctv] The license has ended, so the cameras are not being read. Records and Excel files still work.')
        return

    if args.show:
        try:
            cv2.namedWindow('test')
            cv2.destroyWindow('test')
        except cv2.error:
            print("[cctv] This OpenCV build can't open windows; ignoring --show. "
                  "Watch it on the Live page of the gate app instead (start_gate.bat).")
            args.show = False

    log = GateLog(Store(cfg['db']), cfg['snapshots'], cfg['excel_dir'], cfg['language'], cfg['cooldown_s'])
    previews, stop = ({} if args.show else None), threading.Event()
    th = threading.Thread(target=watch, daemon=True,
                          args=(cam, cfg, Recognizer(cfg['max_side'], cfg['use_cuda'], vertical_every=3), threading.Lock(),
                                Lane(one_lane(cam), cfg, log), previews, stop))
    th.start()
    print(f"[cctv] logging to {cfg['db']} and {cfg['excel_dir']}  (Ctrl+C to stop)")
    try:
        while th.is_alive():
            if previews is not None:   # OpenCV windows must be driven from the main thread
                for name, img in list(previews.items()):
                    cv2.imshow(name, img)
                if cv2.waitKey(50) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.5)
            log.flush()
    except KeyboardInterrupt:
        pass
    stop.set()
    th.join(timeout=5)
    log.flush()
    if args.show:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
