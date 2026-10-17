"""Gate OCR web app:  py -3.12 server.py   then open http://localhost:8000

Serves the API (/api/...) and the React app built from web/ (cd web && npm run build).
Detection itself runs in the gate service (cctv.py), configured through cameras.json;
records come from the database it writes (see src/config.py).
"""
import argparse
import base64
import hashlib
import hmac
import secrets
import shutil
import socket
import tempfile
import threading
import time
import webbrowser
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

# Imports the OCR code first: on Windows, a library loaded earlier (pandas was one) can make
# onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src import config  # noqa: I001

import cv2
import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from cctv import DEFAULTS, _safe
from src.camera import hikvision_url, port_open, redact
from src.gate import GateLog, GateTracker
from src.i18n import LANGUAGES, TEXT
from src.iso6346 import format_code
from src.recognizer import Recognizer, draw
from src.store import Store, needs_review, parse_fix, to_excel, to_zip

WEB = config.ROOT / 'web' / 'dist'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
OFFLINE_S = 15       # a camera with no new picture for this long is shown as offline
STARTING_S = 30      # after "Start detection", how long the page says "starting"
MAX_UPLOAD = 25 << 20  # bytes per uploaded photo
MAX_VIDEO = 4 << 30    # bytes per uploaded video
_started_at = 0.0
_ocr_lock = threading.Lock()  # one OCR at a time: it already uses every CPU core
COOKIE, SESSION_S = 'gate_session', 30 * 24 * 3600
OPEN_API = {'/api/health', '/api/text', '/api/auth', '/api/login'}  # usable before logging in
MAX_TRIES, TRIES_WINDOW_S = 10, 300  # wrong passwords per device before it has to wait
_failures: dict[str, list[float]] = {}

app = FastAPI(title='Container Gate OCR')


# ---------- site login ----------
# One password per site, stored as a salted PBKDF2 hash in cameras.json. A login is a signed
# cookie (expiry + HMAC with a per-site secret); changing the password changes the secret, which
# logs every device out. Until a password is set, the API answers only the gate computer itself.

def hash_password(password, salt=None, rounds=200_000):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), rounds).hex()
    return f'pbkdf2_sha256${rounds}${salt}${digest}'


def check_password(password, stored):
    try:
        _, rounds, salt, _ = stored.split('$')
        return hmac.compare_digest(hash_password(password, salt, int(rounds)), stored)
    except (AttributeError, ValueError):
        return False


def _session(secret, expires):
    return f"{expires}.{hmac.new(bytes.fromhex(secret), str(expires).encode(), 'sha256').hexdigest()}"


def _logged_in(cfg, cookie):
    try:
        expires = int((cookie or '').split('.')[0])
    except ValueError:
        return False
    return expires > time.time() and hmac.compare_digest(_session(cfg.get('session_secret', '00'), expires), cookie)


def _is_local(request):
    return request.client is not None and request.client.host in ('127.0.0.1', '::1')


def _log_in(response, cfg):
    expires = int(time.time()) + SESSION_S
    response.set_cookie(COOKIE, _session(cfg['session_secret'], expires), max_age=SESSION_S,
                        httponly=True, samesite='strict')


@app.middleware('http')
async def site_login(request: Request, call_next):
    path = request.url.path
    if path.startswith('/api/') and path not in OPEN_API:
        cfg = config.load_config()
        if not cfg.get('site_password'):
            if not _is_local(request):
                return JSONResponse({'detail': {'errors': ['local_only']}}, 403)
        elif not _logged_in(cfg, request.cookies.get(COOKIE)):
            return JSONResponse({'detail': {'errors': ['login_needed']}}, 401)
    return await call_next(request)


@app.get('/api/auth')
def auth(request: Request):
    cfg = config.load_config()
    return {'password_set': bool(cfg.get('site_password')), 'local': _is_local(request),
            'logged_in': _logged_in(cfg, request.cookies.get(COOKIE))}


class Login(BaseModel):
    password: str


@app.post('/api/login')
def login(body: Login, request: Request, response: Response):
    """Wrong passwords are slowed down, and too many in a row make that device wait."""
    who = request.client.host if request.client else '?'
    now = time.time()
    recent = _failures[who] = [t for t in _failures.get(who, []) if now - t < TRIES_WINDOW_S]
    if len(recent) >= MAX_TRIES:
        raise HTTPException(429, {'errors': ['too_many_tries']})
    cfg = config.load_config()
    if not cfg.get('site_password'):
        raise HTTPException(409, {'errors': ['no_password']})
    if not check_password(body.password, cfg['site_password']):
        recent.append(now)
        time.sleep(1)
        raise HTTPException(401, {'errors': ['wrong_password']})
    _failures.pop(who, None)
    _log_in(response, cfg)
    return {'ok': True}


@app.post('/api/logout')
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {'ok': True}


class NewPassword(BaseModel):
    current: str = ''
    new: str


@app.put('/api/password')
def set_password(body: NewPassword, response: Response):
    """Set the site password (first time: only from the gate computer, see site_login) or
    change it (needs the current one). Every other device is logged out."""
    cfg = config.load_config()
    if cfg.get('site_password') and not check_password(body.current, cfg['site_password']):
        time.sleep(1)
        raise HTTPException(403, {'errors': ['wrong_password']})
    if len(body.new) < 6:
        raise HTTPException(422, {'errors': ['short_password']})
    cfg.update(site_password=hash_password(body.new), session_secret=secrets.token_hex(32))
    config.save_config(cfg)
    _log_in(response, cfg)
    return {'ok': True}


@app.get('/api/health')
def health():
    return {'ok': True}


@app.get('/api/text')
def text():
    """All app text: {'languages': {'en': 'English', ...}, 'text': {key: [english, arabic]}}."""
    return {'languages': LANGUAGES, 'text': TEXT}


@lru_cache
def get_store():
    return Store(str(config.ROOT / DEFAULTS['db']))


def _enabled_cameras():
    return [c for c in config.load_config().get('cameras', []) if c.get('enabled', True)]


@app.get('/api/status')
def status():
    """Detection service and camera states for the Live page. A camera's state is 'ok',
    'connecting', 'offline' (no picture for `age` s; age None if never) or 'stopped'."""
    running, cams = config.service_status()
    now, out = time.time(), []
    for cam in _enabled_cameras():
        s = cams.get(cam['name'])
        age = int(now - s['last_frame_at']) if s and s.get('last_frame_at') else None
        state = ('stopped' if not running else 'connecting' if not s
                 else 'offline' if age is None or age > OFFLINE_S else 'ok')
        out.append({'name': cam['name'], 'direction': cam.get('direction', 'IN'), 'location': cam.get('location', ''),
                    'state': state, 'age': age,
                    'has_picture': running and (config.LIVE / f"{_safe(cam['name'])}.jpg").is_file()})
    return {'running': running, 'starting': not running and time.time() - _started_at < STARTING_S,
            'today': date.today().isoformat(), 'cameras': out}


@app.post('/api/service/start')
def service_start():
    global _started_at
    running, _ = config.service_status()
    if not running and time.time() - _started_at >= STARTING_S:  # don't start it twice
        config.start_service()
        _started_at = time.time()
    return {'ok': True}


@app.get('/api/live/{name}.jpg')
def live_picture(name: str):
    """The newest annotated picture of a camera (written by the detection service)."""
    path = config.LIVE / f'{_safe(name)}.jpg'
    if name not in {c['name'] for c in _enabled_cameras()} or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={'Cache-Control': 'no-store'})


class Settings(BaseModel):
    ip: str = ''
    user: str = 'admin'
    password: str = ''              # empty: keep the saved password
    port: int = Field(554, ge=1, le=65535)
    language: Literal['en', 'ar'] = 'en'


@app.get('/api/settings')
def get_settings():
    """NVR login (never the password, only whether one is saved), Excel language and cameras."""
    cfg = config.load_config()
    nvr = cfg.get('nvr', {})
    return {'nvr': {'ip': nvr.get('ip', ''), 'user': nvr.get('user', 'admin'), 'port': nvr.get('port', 554),
                    'has_password': bool(nvr.get('password'))},
            'language': cfg.get('language', 'en'), 'cameras': [_safe_camera(c) for c in cfg.get('cameras', [])]}


def _safe_camera(cam):
    """A camera entry without secrets: its own password, or one inside an rtsp:// source URL."""
    cam = {k: v for k, v in cam.items() if k != 'password'}
    if 'source' in cam:
        cam['source'] = redact(cam['source'])
    return cam


@app.put('/api/settings')
def put_settings(new: Settings):
    """Save the NVR login and Excel language. An NVR address this computer can't reach is
    refused (422 {'detail': {'errors': ['unreachable']}}): usually a typo or a cable problem."""
    ip = new.ip.strip()
    if ip and not port_open(ip, new.port):
        raise HTTPException(422, {'errors': ['unreachable']})
    cfg = config.load_config()
    password = new.password or cfg.get('nvr', {}).get('password', '')
    cfg.update(nvr={'ip': ip, 'user': new.user.strip(), 'password': password, 'port': new.port}, language=new.language)
    config.save_config(cfg)
    return get_settings()


def _camera(cfg, name):
    cam = next((c for c in cfg.get('cameras', []) if c['name'] == name), None)
    if cam is None:
        raise HTTPException(404)
    return cam


class CameraSwitch(BaseModel):
    enabled: bool


@app.patch('/api/cameras/{name}')
def switch_camera(name: str, change: CameraSwitch):
    """Switch a camera on or off; the detection service follows within a few seconds."""
    cfg = config.load_config()
    _camera(cfg, name)['enabled'] = change.enabled
    config.save_config(cfg)
    return get_settings()


@app.delete('/api/cameras/{name}')
def delete_camera(name: str):
    """Remove a camera. Trucks it already logged stay in the records."""
    cfg = config.load_config()
    cfg['cameras'].remove(_camera(cfg, name))
    config.save_config(cfg)
    return get_settings()


class NewCamera(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    channel: int = Field(ge=1, le=64)
    direction: Literal['IN', 'OUT'] = 'IN'
    location: str = ''
    roi: list[float] | None = None  # reading area [left, top, right, bottom], fractions of the picture


def _check_roi(roi):
    if roi is not None and not (len(roi) == 4 and 0 <= roi[0] < roi[2] <= 1 and 0 <= roi[1] < roi[3] <= 1):
        raise HTTPException(422, {'errors': ['bad_area']})


@app.post('/api/cameras')
def add_camera(cam: NewCamera):
    """Add a camera, or replace the one with the same name (in its place). Detection starts on
    it within a few seconds."""
    _check_roi(cam.roi)
    new = {'name': cam.name, 'channel': cam.channel, 'direction': cam.direction,
           'location': cam.location.strip(), 'enabled': True}
    if cam.roi:
        new['roi'] = [round(v, 3) for v in cam.roi]
    cfg = config.load_config()
    cams = cfg.setdefault('cameras', [])
    i = next((i for i, c in enumerate(cams) if c['name'] == cam.name), len(cams))
    cams[i:i + 1] = [new]
    cfg.setdefault('autostart', True)
    config.save_config(cfg)
    return get_settings()


class Channel(BaseModel):
    channel: int = Field(ge=1, le=64)
    roi: list[float] | None = None


def _grab(channel):
    """One picture from an NVR channel, with the saved login. Problems come back as text keys:
    no_nvr (not set up), unreachable (network), no_video (login, channel or RTSP setting)."""
    nvr = config.load_config().get('nvr', {})
    if not nvr.get('ip'):
        raise HTTPException(422, {'errors': ['no_nvr']})
    port = nvr.get('port', 554)
    if not port_open(nvr['ip'], port):
        raise HTTPException(422, {'errors': ['unreachable']})
    frame = config.grab_frame(hikvision_url(nvr['ip'], nvr.get('user', ''), nvr.get('password', ''), channel, port=port))
    if frame is None:
        raise HTTPException(422, {'errors': ['no_video']})
    return frame


def _jpeg(img, max_width=1600):
    """JPEG bytes, scaled down to max_width (plenty for a screen, much less to send)."""
    if img.shape[1] > max_width:
        f = max_width / img.shape[1]
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


@app.post('/api/cameras/frame')
def camera_frame(req: Channel):
    """The camera's current picture, for drawing its reading area."""
    return Response(_jpeg(_grab(req.channel)), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


@app.post('/api/cameras/test')
def camera_test(req: Channel):
    """Read the camera's current picture (only its reading area, like the detection service)."""
    _check_roi(req.roi)
    frame = _grab(req.channel)
    if req.roi:
        H, W = frame.shape[:2]
        x0, y0, x1, y1 = req.roi
        frame = frame[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
    return read_image(frame)


@lru_cache(maxsize=2)  # each copy of the models is ~100 MB
def get_recognizer(max_side=1920):
    return Recognizer(max_side=max_side)


def read_image(img, max_side=1920, **opts):
    """What the OCR reads in a picture, for the browser: container codes, plates, all text,
    time taken, and the picture with the boxes drawn (a data: URL)."""
    with _ocr_lock:
        out = get_recognizer(max_side)(img, **opts)
    shown = draw(img.copy(), out['codes'], out['plates'])
    return {
        'ms': round(out['ms']),
        'codes': [{'code': format_code(c['code']), 'valid': bool(c['valid']), 'readable': not c['code'].endswith('?'),
                   'size_type': c['size_type'] or '', 'score': round(float(c['score']), 2)} for c in out['codes']],
        'plates': [{'plate': p['plate'], 'arabic': p['arabic'], 'verified': bool(p['verified']),
                    'score': round(float(p['score']), 2)} for p in out['plates']],
        'texts': [str(x) for x in out['texts']],
        'image': 'data:image/jpeg;base64,' + base64.b64encode(_jpeg(shown)).decode(),
    }


class OcrOptions(BaseModel):
    max_side: Literal[960, 1280, 1600, 1920, 2560] = 1920
    zoom: bool = True
    vertical: bool = True
    plates: bool = True


@app.post('/api/ocr')
def ocr_photo(file: UploadFile = File(...), max_side: int = Form(1920), zoom: bool = Form(True),
              vertical: bool = Form(True), plates: bool = Form(True)):
    """Read an uploaded photo (Test page)."""
    try:
        opts = OcrOptions(max_side=max_side, zoom=zoom, vertical=vertical, plates=plates)
    except ValueError:
        raise HTTPException(422, {'errors': ['bad_options']}) from None
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, {'errors': ['too_big']})
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(422, {'errors': ['bad_image']})
    return read_image(img, **opts.model_dump())


def _samples():
    """Sample photos shipped with the app: {name: path}."""
    files = sorted(p for p in (config.ROOT / 'images').glob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg'))
    return {p.name: p for p in files + [config.ROOT / 'demo_input.jpg'] if p.is_file()}


@app.get('/api/samples')
def samples():
    return list(_samples())


class SampleRequest(OcrOptions):
    name: str


@app.post('/api/ocr/sample')
def ocr_sample(req: SampleRequest):
    path = _samples().get(req.name)
    if path is None:
        raise HTTPException(404)
    return read_image(cv2.imread(str(path)), **req.model_dump(exclude={'name'}))


class StreamRequest(OcrOptions):
    url: str


@app.post('/api/stream/frame')
def ocr_stream(req: StreamRequest):
    """Read one picture from a camera stream address (Test page). Only network streams: OpenCV
    would otherwise also open files on this computer."""
    if not req.url.strip().lower().startswith(('rtsp://', 'http://', 'https://')):
        raise HTTPException(422, {'errors': ['bad_url']})
    frame = config.grab_frame(req.url.strip())
    if frame is None:
        raise HTTPException(422, {'errors': ['camera_error']})
    return read_image(frame, **req.model_dump(exclude={'url'}))


class VideoJob:
    """A video played through the gate pipeline in the background, as if it were a camera:
    trucks are confirmed across frames and logged to a temporary database (never the real one)."""

    def __init__(self, work):
        self.work, self.progress, self.seconds, self.ids = work, 0.0, 0.0, []
        self.done, self.error, self.cancel, self.frame = False, None, False, None
        self.started = time.time()
        self.store = Store(str(work / 'gate.db'))

    def run(self, path, fps, min_hits, direction, location, opts):
        try:
            cap = cv2.VideoCapture(str(path))
            vfps = cap.get(cv2.CAP_PROP_FPS) or 25
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            step = max(1, round(vfps / fps))
            tracker = GateTracker(min_hits=min_hits)
            log = GateLog(self.store, self.work / 'snapshots', self.work / 'excel')
            n = 0
            while not self.cancel:
                ok, frame = cap.read()
                if not ok:
                    break
                n += 1
                if n % step:
                    continue
                with _ocr_lock:
                    out = get_recognizer(opts['max_side'])(frame, **{k: v for k, v in opts.items() if k != 'max_side'})
                self._log(log, tracker.update(out['codes'], frame, n / vfps, out['plates']), direction, location)
                self.frame = _jpeg(draw(frame, out['codes'], out['plates']), 960)
                self.progress, self.seconds = min(1.0, n / total), n / vfps
            cap.release()
            if n == 0:
                self.error = 'bad_video'
            self._log(log, tracker.flush(n / vfps), direction, location)
            self.progress = 1.0
        except Exception as e:  # noqa: BLE001  (shown on the page; details in the server window)
            print(f'[server] video test failed: {e!r}')
            self.error = 'video_failed'
        finally:
            self.done = True
            if self.cancel:
                self.discard()

    def _log(self, log, events, direction, location):
        for e in events:
            r = log.log(e, 'Video test', location, direction)
            if r['status'] == 'added':
                self.ids.append(r['id'])

    def rows(self):
        return [_public(self.store.get(i)) for i in self.ids]

    def discard(self):
        self.store.db.close()
        shutil.rmtree(self.work, ignore_errors=True)


_jobs: dict[str, VideoJob] = {}


def _job(job_id):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404)
    return job


@app.post('/api/video')
def video_start(file: UploadFile = File(...), fps: float = Form(2.0), min_hits: int = Form(2),
                direction: str = Form('IN'), location: str = Form(''), max_side: int = Form(1920),
                zoom: bool = Form(True), vertical: bool = Form(True), plates: bool = Form(True)):
    """Start reading an uploaded video in the background; returns {'job': id}. One video at a
    time: starting one discards the previous one and its temporary files."""
    try:
        opts = OcrOptions(max_side=max_side, zoom=zoom, vertical=vertical, plates=plates).model_dump()
    except ValueError:
        raise HTTPException(422, {'errors': ['bad_options']}) from None
    if not (0.5 <= fps <= 5 and 1 <= min_hits <= 5 and direction in ('IN', 'OUT')):
        raise HTTPException(422, {'errors': ['bad_options']})
    for old in _jobs.values():
        old.cancel = True
        if old.done:
            old.discard()
    _jobs.clear()
    work = Path(tempfile.mkdtemp(prefix='gate_video_'))
    path = work / ('video' + Path(file.filename or '').suffix.lower())
    with open(path, 'wb') as f:
        while chunk := file.file.read(1 << 20):
            if f.tell() + len(chunk) > MAX_VIDEO:
                f.close()
                shutil.rmtree(work, ignore_errors=True)
                raise HTTPException(413, {'errors': ['too_big']})
            f.write(chunk)
    job_id, job = secrets.token_hex(8), VideoJob(work)
    _jobs[job_id] = job
    threading.Thread(target=job.run, args=(path, fps, min_hits, direction, location.strip(), opts), daemon=True).start()
    return {'job': job_id}


@app.get('/api/video/{job_id}')
def video_status(job_id: str):
    job = _job(job_id)
    return {'progress': round(job.progress, 3), 'seconds': round(job.seconds, 1), 'done': job.done,
            'error': job.error, 'elapsed': round(time.time() - job.started), 'rows': job.rows()}


@app.get('/api/video/{job_id}/frame.jpg')
def video_frame(job_id: str):
    """The last picture read, with its boxes."""
    frame = _job(job_id).frame
    if frame is None:
        raise HTTPException(404)
    return Response(frame, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


@app.get('/api/video/{job_id}/records/{rid}/{kind}')
def video_photo(job_id: str, rid: int, kind: Literal['snapshot', 'plate_image']):
    return record_photo(rid, kind, _job(job_id).store)


@app.get('/api/video/{job_id}/excel')
def video_excel(job_id: str, lang: str = 'en'):
    job = _job(job_id)
    return _download(to_excel([job.store.get(i) for i in job.ids], lang), 'gate_log_video_test.xlsx', XLSX)


def _public(row):
    """A stored row for the browser: photo paths on this computer are replaced by yes/no."""
    return {**row, 'needs_review': needs_review(row),
            'snapshot': bool(row.get('snapshot')), 'plate_image': bool(row.get('plate_image'))}


@app.get('/api/records')
def records(day: date, store: Store = Depends(get_store)):
    """One day's trucks, oldest first."""
    return [_public(r) for r in store.day(day.isoformat())]


@app.get('/api/records/{rid}/{kind}')
def record_photo(rid: int, kind: Literal['snapshot', 'plate_image'], store: Store = Depends(get_store)):
    """A truck's snapshot or plate close-up. Looked up by record id, so only photos that
    belong to a record can be fetched."""
    row = store.get(rid)
    path = row and row.get(kind)
    if not path or not Path(path).is_file():
        raise HTTPException(404)
    return FileResponse(path)


class Fix(BaseModel):
    plate: str = ''
    container: str = ''
    direction: Literal['IN', 'OUT']


@app.patch('/api/records/{rid}')
def fix_record(rid: int, fix: Fix, store: Store = Depends(get_store)):
    """A person corrects a reading. Bad input -> 422 {'detail': {'errors': [text keys]}}.
    Saved -> the updated row, and warning 'check_digit_wrong' if the container's check digit
    doesn't match (saved anyway)."""
    row = store.get(rid)
    if not row:
        raise HTTPException(404)
    fields, errors = parse_fix(fix.plate, fix.container, fix.direction)
    if errors:
        raise HTTPException(422, {'errors': errors})
    config.save_fix(store, row, fields)
    return {'row': _public(store.get(rid)), 'warning': 'check_digit_wrong' if fields['check_digit_ok'] == 0 else None}


def _download(data, name, media_type):
    return Response(data, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="{name}"'})


@app.get('/api/excel/day/{day}')
def excel_day(day: date, lang: str = 'en', store: Store = Depends(get_store)):
    return _download(to_excel(store.day(day.isoformat()), lang), f'gate_log_{day}.xlsx', XLSX)


@app.get('/api/excel/month/{month}')
def excel_month(month: Annotated[str, PathParam(pattern=r'^\d{4}-\d{2}$')], lang: str = 'en',
                store: Store = Depends(get_store)):
    return _download(to_excel(store.month(month), lang), f'gate_log_{month}.xlsx', XLSX)


@app.get('/api/zip/day/{day}')
def zip_day(day: date, lang: str = 'en', store: Store = Depends(get_store)):
    """The day's Excel plus every truck's photos; built when asked for (it can be large)."""
    return _download(to_zip(store.day(day.isoformat()), lang, f'gate_log_{day}'), f'gate_log_{day}.zip', 'application/zip')


if WEB.is_dir():  # last, so /api/... routes win
    app.mount('/', StaticFiles(directory=WEB, html=True), name='web')


def lan_address():
    """This computer's address on the site network (what other computers and phones type in)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(('10.255.255.255', 1))  # sends nothing; just picks the network interface
            return s.getsockname()[0]
        except OSError:
            return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # the whole network; until a site password is set, the API answers only this computer
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--open', action='store_true', help='open the app in the browser once it is running')
    args = ap.parse_args()
    if not WEB.is_dir():
        print(f'[server] {WEB} is missing: build the app first (cd web && npm install && npm run build)')
    for leftover in Path(tempfile.gettempdir()).glob('gate_video_*'):  # video tests from an earlier run
        shutil.rmtree(leftover, ignore_errors=True)
    print(f'[server] Gate app on this computer: http://localhost:{args.port}')
    if (ip := lan_address()) and args.host == '0.0.0.0':
        print(f'[server] Other computers and phones on the network: http://{ip}:{args.port} '
              f'(after a site password is chosen in the app)')
    if args.open:
        threading.Timer(1.5, webbrowser.open, [f'http://localhost:{args.port}']).start()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
