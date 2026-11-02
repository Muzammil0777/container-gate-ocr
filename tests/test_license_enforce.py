"""After the grace period: detection stops, new cameras and video tests are refused, records and
downloads keep working; a renewed key brings it all back (Task 14)."""
from datetime import date, timedelta

import cctv
from tests.test_server import client, licensed, no_real_settings, site  # noqa: F401  (shared fixtures)

ENDED = '2020-01-01'  # long past the grace days


def _ends(store, make, expires):
    store.meta_set('license_key', make(expires=expires))  # set directly: activation refuses an ended key


def test_after_grace_new_cameras_and_videos_are_refused_but_records_work(licensed):
    _, make, store = licensed
    store.add({'date': '2026-10-17', 'time': '09:00:00', 'direction': 'IN', 'plate': '3231 UTA'})
    _ends(store, make, ENDED)
    r = client.post('/api/cameras', json={'name': 'Gate 3', 'channel': 3})
    assert r.status_code == 403 and r.json()['detail'] == {'errors': ['license_banner_expired']}
    r = client.post('/api/video', files={'file': ('v.mp4', b'x')})
    assert r.status_code == 403 and r.json()['detail'] == {'errors': ['license_banner_expired']}
    assert len(client.get('/api/records?day=2026-10-17').json()) == 1
    assert client.get('/api/excel/day/2026-10-17').status_code == 200
    assert client.get('/api/excel/month/2026-10').status_code == 200
    assert client.get('/api/zip/day/2026-10-17').status_code == 200

    _ends(store, make, '2099-01-01')  # renewed
    assert client.post('/api/cameras', json={'name': 'Gate 3', 'channel': 3}).status_code == 200


def test_grace_days_still_allow_new_cameras(licensed):
    _, make, store = licensed
    _ends(store, make, (date.today() - timedelta(days=3)).isoformat())
    assert client.post('/api/cameras', json={'name': 'Gate 3', 'channel': 3}).status_code == 200


class FakeManager:
    def __init__(self, store):
        self.store, self.lanes, self.stopped = store, {'Lane 1': None, 'Gate 2': None}, []

    def stop(self, name):
        self.stopped.append(name)
        self.lanes.pop(name)


def test_service_stops_the_cameras_after_grace_and_resumes_with_a_new_key(licensed):
    _, make, store = licensed
    manager = FakeManager(store)
    assert cctv.follow_license(manager, None) is True and manager.stopped == []  # trial
    _ends(store, make, ENDED)
    assert cctv.follow_license(manager, True) is False
    assert manager.stopped == ['Lane 1', 'Gate 2'] and manager.lanes == {}
    _ends(store, make, '2099-01-01')
    assert cctv.follow_license(manager, False) is True
