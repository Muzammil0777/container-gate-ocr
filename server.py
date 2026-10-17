"""Gate OCR web app:  py -3.12 server.py   then open http://localhost:8000

Serves the API (/api/...) and the React app built from web/ (cd web && npm run build).
Detection itself runs in the gate service (cctv.py), configured through cameras.json;
records come from the database it writes (see src/config.py).
"""
import argparse
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

# Imports the OCR code first: on Windows, a library loaded earlier (e.g. by pandas) can make
# onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src import config  # noqa: I001

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cctv import DEFAULTS, _safe
from src.i18n import LANGUAGES, TEXT
from src.store import Store, needs_review, parse_fix, to_excel, to_zip

WEB = config.ROOT / 'web' / 'dist'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
OFFLINE_S = 15       # a camera with no new picture for this long is shown as offline
STARTING_S = 30      # after "Start detection", how long the page says "starting"
_started_at = 0.0

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
