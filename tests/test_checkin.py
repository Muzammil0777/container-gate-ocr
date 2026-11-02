"""Heartbeat to the Control Center (Task 16), against a local stand-in speaking the check-in contract."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import server
from src import checkin
from tests.test_server import client, licensed, no_real_settings, site  # noqa: F401  (shared fixtures)


@pytest.fixture
def control_center():
    """A local Control Center: answers with cc.answer (dict, or an HTTP status code) and keeps the bodies."""
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            cc.bodies.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            code, out = (cc.answer, {'detail': 'Unknown license for this machine.'}) if isinstance(cc.answer, int) \
                else (200, cc.answer)
            self.send_response(code)
            self.end_headers()
            self.wfile.write(json.dumps(out).encode())

        def log_message(self, *a):
            pass

    httpd = HTTPServer(('127.0.0.1', 0), Handler)
    cc = type('CC', (), {'answer': {'status': 'active'}, 'bodies': [],
                         'url': f'http://127.0.0.1:{httpd.server_port}/v1/checkin'})
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield cc
    httpd.shutdown()


def _beat(store, cc_url):
    return checkin.checkin(store, server.site_health(store), '1.4.0', url=cc_url)


def test_sends_the_contract_without_plates_or_containers(licensed, control_center):
    _, make, store = licensed
    store.meta_set('license_key', make())
    store.add({'date': time.strftime('%Y-%m-%d'), 'time': '09:00:00', 'direction': 'IN',
               'plate': '3231 UTA', 'container': 'MSCU 123456 5'})
    assert _beat(store, control_center.url) is True
    body = control_center.bodies[0]
    assert set(body) == {'license_id', 'machine', 'version', 'edition', 'state', 'health'}
    assert (body['license_id'], body['version'], body['state']) == ('L-1', '1.4.0', 'active')
    assert body['health']['trucks_today'] == 1 and body['health']['check_rows_today'] == 1
    assert body['health']['last_truck_at'].endswith('T09:00:00') and body['health']['cameras_total'] == 2
    assert '3231' not in json.dumps(body) and 'MSCU' not in json.dumps(body)
    assert store.meta_get('checkin_at')


def test_a_renewal_is_saved_and_shown_at_once(licensed, control_center):
    _, make, store = licensed
    store.meta_set('license_key', make(expires='2027-01-01'))
    control_center.answer = {'status': 'active', 'key': make(expires='2028-01-01', lid='L-2')}
    _beat(store, control_center.url)
    assert client.get('/api/license').json()['ends'] == '2028-01-01'


def test_a_renewal_key_for_another_computer_is_ignored(licensed, control_center):
    _, make, store = licensed
    store.meta_set('license_key', make(expires='2027-01-01'))
    control_center.answer = {'status': 'active', 'key': make(machine='AAAA-BBBB-CCCC', expires='2028-01-01')}
    _beat(store, control_center.url)
    assert client.get('/api/license').json()['ends'] == '2027-01-01'


def test_ended_stops_the_license_and_active_brings_it_back(licensed, control_center):
    _, make, store = licensed
    store.meta_set('license_key', make())
    control_center.answer = {'status': 'ended'}
    _beat(store, control_center.url)
    lic = client.get('/api/license').json()
    assert lic['state'] == 'expired' and lic['days_left'] == 0
    assert client.post('/api/cameras', json={'name': 'Gate 3', 'channel': 3}).status_code == 403
    control_center.answer = {'status': 'active'}                       # contract reopened
    _beat(store, control_center.url)
    assert client.get('/api/license').json()['state'] == 'active'


@pytest.mark.parametrize('trouble', ['refused_403', 'down', 'no_address', 'trial'])
def test_offline_down_or_unknown_license_changes_nothing(licensed, control_center, trouble):
    _, make, store = licensed
    if trouble != 'trial':
        store.meta_set('license_key', make())
    before = client.get('/api/license').json()
    control_center.answer = 403                                         # a key made offline with license_tool.py
    url = {'down': 'http://127.0.0.1:9/v1/checkin', 'no_address': ''}.get(trouble, control_center.url)
    assert _beat(store, url) is False
    assert client.get('/api/license').json() == before and store.meta_get('checkin_at') is None


def test_check_now_runs_a_check_in_and_shows_its_time(licensed, control_center, monkeypatch):
    _, make, store = licensed
    store.meta_set('license_key', make())
    monkeypatch.setattr(checkin, 'URL', control_center.url)
    body = client.post('/api/license/checkin', json={}).json()
    assert body['checkin_on'] is True and body['checkin_at'] and len(control_center.bodies) == 1


def test_check_now_offline_shows_no_error(licensed, monkeypatch):
    _, make, store = licensed
    store.meta_set('license_key', make())
    monkeypatch.setattr(checkin, 'URL', 'http://127.0.0.1:9/v1/checkin')
    r = client.post('/api/license/checkin', json={})
    assert r.status_code == 200 and r.json()['checkin_at'] is None


def test_checkin_texts_exist_in_both_languages():
    for k in ('license_checkin_at', 'license_checkin_never', 'help_checkin', 'check_now', 'license_version',
              'license_users', 'license_lanes', 'license_lanes_any', 'license_edition_site', 'license_edition_enterprise'):
        assert all(server.TEXT[k]), k
