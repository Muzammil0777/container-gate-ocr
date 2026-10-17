"""The web API (server.py), through FastAPI's test client."""
import io
import json
import time
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

import server
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


def test_record_photos(site):
    tmp_path, store = site
    snap = tmp_path / 'snap.jpg'
    snap.write_bytes(b'snap')
    _, rid = store.add({'date': '2026-10-17', 'time': '09:00:00', 'direction': 'IN', 'plate': '3231 UTA',
                        'snapshot': str(snap), 'plate_image': str(tmp_path / 'deleted.jpg')})
    assert client.get(f'/api/records/{rid}/snapshot').content == b'snap'
    assert client.get(f'/api/records/{rid}/plate_image').status_code == 404    # file gone
    assert client.get(f'/api/records/{rid + 1}/snapshot').status_code == 404   # no such record
    assert client.get(f'/api/records/{rid}/camera').status_code == 422         # not a photo field


def test_fix_record(site, monkeypatch):
    tmp_path, store = site
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    _, rid = store.add({'date': '2026-10-17', 'time': '09:00:00', 'direction': 'IN', 'plate': '231 UTA'})
    r = client.patch(f'/api/records/{rid}', json={'plate': '3231 uta', 'container': 'MRSU 442576 1', 'direction': 'OUT'})
    assert r.status_code == 200 and r.json()['warning'] is None
    row = r.json()['row']
    assert (row['plate'], row['container'], row['direction'], row['corrected']) == ('3231 UTA', 'MRSU 442576 1', 'OUT', 1)
    assert row['needs_review'] is False
    assert (tmp_path / 'logs' / 'excel' / 'gate_log_2026-10-17.xlsx').is_file()
    assert (tmp_path / 'logs' / 'corrections.jsonl').is_file()


def test_fix_record_check_digit_and_bad_input(site, monkeypatch):
    tmp_path, store = site
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    _, rid = store.add({'date': '2026-10-17', 'time': '09:00:00', 'direction': 'IN', 'plate': '3231 UTA'})
    r = client.patch(f'/api/records/{rid}', json={'plate': '3231 UTA', 'container': 'MRSU 442576 2', 'direction': 'IN'})
    assert r.json()['warning'] == 'check_digit_wrong' and r.json()['row']['check_digit_ok'] == 0
    r = client.patch(f'/api/records/{rid}', json={'plate': 'nonsense', 'container': 'MRSU 1', 'direction': 'IN'})
    assert r.status_code == 422 and r.json()['detail'] == {'errors': ['bad_plate', 'bad_container']}
    assert store.get(rid)['container'] == 'MRSU 442576 2'                           # nothing saved
    assert client.patch(f'/api/records/{rid + 1}', json={'direction': 'IN'}).status_code == 404
    assert client.patch(f'/api/records/{rid}', json={'direction': 'UP'}).status_code == 422


def test_month_excel_and_day_zip(site):
    tmp_path, store = site
    snap = tmp_path / 'snap.jpg'
    snap.write_bytes(b'jpg')
    store.add({'date': '2026-10-17', 'time': '09:00:00', 'direction': 'IN', 'plate': '3231 UTA', 'snapshot': str(snap)})
    r = client.get('/api/excel/month/2026-10')
    assert r.status_code == 200 and r.content[:2] == b'PK' and 'gate_log_2026-10.xlsx' in r.headers['content-disposition']
    assert client.get('/api/excel/month/2026-1').status_code == 422
    r = client.get('/api/zip/day/2026-10-17')
    assert sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == ['gate_log_2026-10-17.xlsx', 'photos/snap.jpg']


def test_settings_never_return_the_password(site, monkeypatch):
    monkeypatch.setattr(server, 'port_open', lambda ip, port: True)
    body = {'ip': ' 192.168.1.64 ', 'user': 'admin', 'password': 's3cret', 'port': 554, 'language': 'ar'}
    r = client.put('/api/settings', json=body)
    assert r.status_code == 200 and 's3cret' not in r.text
    assert r.json()['nvr'] == {'ip': '192.168.1.64', 'user': 'admin', 'port': 554, 'has_password': True}
    assert 's3cret' not in client.get('/api/settings').text
    client.put('/api/settings', json={**body, 'password': ''})                   # blank: keep the old one
    assert config.load_config()['nvr']['password'] == 's3cret' and config.load_config()['language'] == 'ar'
    assert [c['name'] for c in client.get('/api/settings').json()['cameras']] == ['Gate 1', 'Gate 2', 'Old']


def test_settings_refuse_unreachable_nvr(site, monkeypatch):
    monkeypatch.setattr(server, 'port_open', lambda ip, port: False)
    r = client.put('/api/settings', json={'ip': '10.9.9.9', 'password': 'x'})
    assert r.status_code == 422 and r.json()['detail'] == {'errors': ['unreachable']}
    assert 'nvr' not in config.load_config()
    assert client.put('/api/settings', json={'ip': '', 'port': 70000}).status_code == 422


def test_switch_and_delete_camera(site):
    assert client.patch('/api/cameras/Gate 1', json={'enabled': False}).status_code == 200
    assert client.patch('/api/cameras/Old', json={'enabled': True}).status_code == 200
    assert [c.get('enabled', True) for c in config.load_config()['cameras']] == [False, True, True]
    assert client.delete('/api/cameras/Gate 2').status_code == 200
    assert [c['name'] for c in config.load_config()['cameras']] == ['Gate 1', 'Old']
    assert client.delete('/api/cameras/Nope').status_code == 404
    assert client.patch('/api/cameras/Nope', json={'enabled': True}).status_code == 404


def test_settings_hide_camera_secrets(site):
    cfg = config.load_config()
    cfg['cameras'] += [{'name': 'Direct', 'source': 'rtsp://admin:hunter2@10.0.0.5:554/stream'},
                       {'name': 'Own login', 'channel': 3, 'password': 'hunter2'}]
    config.save_config(cfg)
    r = client.get('/api/settings')
    assert 'hunter2' not in r.text
    assert r.json()['cameras'][3]['source'] == 'rtsp://***@10.0.0.5:554/stream'
