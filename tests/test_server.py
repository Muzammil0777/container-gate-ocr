"""The web API (server.py), through FastAPI's test client."""
import json
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from server import app, get_store
from src import config
from src.i18n import TEXT
from src.store import Store

client = TestClient(app)


def test_health():
    assert client.get('/api/health').json() == {'ok': True}


def test_text_has_both_languages():
    body = client.get('/api/text').json()
    assert body['languages'] == {'en': 'English', 'ar': 'العربية'}
    assert body['text']['nav_live'] == list(TEXT['nav_live'])
    assert all(len(pair) == 2 for pair in body['text'].values())


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site in tmp_path: two cameras, empty database, no detection service running."""
    monkeypatch.setattr(config, 'CONFIG', tmp_path / 'cameras.json')
    monkeypatch.setattr(config, 'LIVE', tmp_path / 'live')
    (tmp_path / 'live').mkdir()
    config.save_config({'cameras': [{'name': 'Gate 1', 'direction': 'IN'},
                                    {'name': 'Gate 2', 'direction': 'OUT'},
                                    {'name': 'Old', 'enabled': False}]})
    store = Store(str(tmp_path / 'gate.db'))
    app.dependency_overrides[get_store] = lambda: store
    yield tmp_path, store
    app.dependency_overrides.clear()


def _service(tmp_path, cameras, updated=None):
    (tmp_path / 'live' / 'status.json').write_text(json.dumps(
        {'updated': updated or time.time(), 'cameras': cameras}), encoding='utf-8')


def test_status_service_not_running(site):
    body = client.get('/api/status').json()
    assert body['running'] is False and body['today'] == date.today().isoformat()
    assert [(c['name'], c['state']) for c in body['cameras']] == [('Gate 1', 'stopped'), ('Gate 2', 'stopped')]


def test_status_camera_states(site):
    tmp_path, _ = site
    _service(tmp_path, {'Gate 1': {'last_frame_at': time.time() - 1}})          # Gate 2 not reported yet
    cams = client.get('/api/status').json()['cameras']
    assert [(c['state'], c['age']) for c in cams] == [('ok', 1), ('connecting', None)]
    _service(tmp_path, {'Gate 1': {'last_frame_at': time.time() - 60}, 'Gate 2': {'last_frame_at': None}})
    cams = client.get('/api/status').json()['cameras']
    assert [(c['state'], c['age']) for c in cams] == [('offline', 60), ('offline', None)]
    _service(tmp_path, {}, updated=time.time() - 60)                            # service died
    assert client.get('/api/status').json()['running'] is False


def test_live_picture_only_for_enabled_cameras(site):
    tmp_path, _ = site
    for name in ('Gate_1', 'Old'):
        (tmp_path / 'live' / f'{name}.jpg').write_bytes(b'jpg')
    assert client.get('/api/live/Gate 1.jpg').content == b'jpg'
    assert client.get('/api/live/Old.jpg').status_code == 404
    assert client.get('/api/live/Gate 2.jpg').status_code == 404               # no picture yet
    assert client.get('/api/live/..%2Fcameras.jpg').status_code == 404


def test_records_hide_photo_paths(site):
    _, store = site
    store.add({'date': '2026-10-17', 'time': '09:00:00', 'direction': 'IN', 'plate': '3231 UTA',
               'plate_verified': 1, 'snapshot': r'C:\gate\logs\snapshots\a.jpg'})
    [row] = client.get('/api/records?day=2026-10-17').json()
    assert row['plate'] == '3231 UTA' and row['snapshot'] is True and row['plate_image'] is False
    assert row['needs_review'] is True                                          # no container
    assert client.get('/api/records?day=2026-10-18').json() == []
    assert client.get('/api/records?day=yesterday').status_code == 422


def test_excel_day(site):
    _, store = site
    store.add({'date': '2026-10-17', 'time': '09:00:00', 'direction': 'IN', 'plate': '3231 UTA'})
    r = client.get('/api/excel/day/2026-10-17?lang=ar')
    assert r.status_code == 200 and r.content[:2] == b'PK'
    assert 'gate_log_2026-10-17.xlsx' in r.headers['content-disposition']
