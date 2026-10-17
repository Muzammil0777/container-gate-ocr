"""Gate OCR web app:  py -3.12 server.py   then open http://localhost:8000

Serves the API (/api/...) and the React app built from web/ (cd web && npm run build).
Detection itself runs in the gate service (cctv.py), configured through cameras.json;
records come from the database it writes (see src/config.py).
"""
import argparse

# Imports the OCR code first: on Windows, a library loaded earlier (e.g. by pandas) can make
# onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src.config import ROOT  # noqa: I001

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.i18n import LANGUAGES, TEXT

WEB = ROOT / 'web' / 'dist'

app = FastAPI(title='Container Gate OCR')


@app.get('/api/health')
def health():
    return {'ok': True}


@app.get('/api/text')
def text():
    """All app text: {'languages': {'en': 'English', ...}, 'text': {key: [english, arabic]}}."""
    return {'languages': LANGUAGES, 'text': TEXT}


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
