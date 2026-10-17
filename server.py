"""Gate OCR web app:  py -3.12 server.py   then open http://localhost:8000

Serves the API (/api/...) and the React app built from web/ (cd web && npm run build).
Detection itself runs in the gate service (cctv.py), configured through cameras.json;
records come from the database it writes (see src/config.py).
"""
import argparse
import base64
import threading
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

# Imports the OCR code first: on Windows, a library loaded earlier (e.g. by pandas) can make
# onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src import config  # noqa: I001

import cv2
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from cctv import DEFAULTS, _safe
from src.camera import hikvision_url, port_open, redact
from src.i18n import LANGUAGES, TEXT
from src.iso6346 import format_code
from src.recognizer import Recognizer, draw
from src.store import Store, needs_review, parse_fix, to_excel, to_zip

WEB = config.ROOT / 'web' / 'dist'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
OFFLINE_S = 15       # a camera with no new picture for this long is shown as offline
STARTING_S = 30      # after "Start detection", how long the page says "starting"
_started_at = 0.0
_ocr_lock = threading.Lock()  # one OCR at a time: it already uses every CPU core

app = FastAPI(title='Container Gate OCR')


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # ponytail: localhost only until the site login exists (tasks/todo.md, Task 11)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    args = ap.parse_args()
    if not WEB.is_dir():
        print(f'[server] {WEB} is missing: build the app first (cd web && npm install && npm run build)')
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
