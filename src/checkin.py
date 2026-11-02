"""Heartbeat to the Control Center (contract: tasks/plan.md, "Control Center").

Every 15 minutes, when online, server.py sends this computer's license, version and health
(cameras, trucks and Check rows today, disk; never plates, containers or photos). The answer
may carry a newer key (a renewal: saved once it checks out) or "ended" (the license stops).
Any failure (no internet, Control Center down, 403 for a key made offline) changes nothing.
"""
import json
import os
import time
import urllib.request
from datetime import date

from src import license

# ponytail: the address is set with Task 17 (Control Center online); until then, empty = off
URL = os.environ.get('GATE_CONTROL_CENTER', '')
EVERY_S, TIMEOUT_S = 15 * 60, 5


def _post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read())


def checkin(store, health, version, url=None, post=_post):
    """Send one heartbeat and apply the answer. True if the Control Center answered, else False
    (no address, no key yet, offline, refused: nothing changes)."""
    url = URL if url is None else url
    lic = license.check(store)
    if not url or not lic['lid']:
        return False
    body = {'license_id': lic['lid'], 'machine': lic['machine'], 'version': version,
            'edition': lic['edition'], 'state': lic['state'], 'health': health}
    try:
        answer = post(url, body)
        status = answer['status']
    except Exception:  # noqa: BLE001  (offline, timeout, HTTP error, bad answer: never bother the gate)
        return False
    store.meta_set('checkin_at', time.strftime('%Y-%m-%dT%H:%M:%S'))
    if status == 'ended':
        if store.meta_get('license_ended') != lic['lid']:
            store.meta_set('license_ended', lic['lid'])
            store.meta_set('license_ended_on', date.today().isoformat())
    elif status == 'active':
        store.meta_set('license_ended', '')
        payload, error = license.read_key(answer.get('key') or '', machine=lic['machine'])
        if payload and not error:  # a renewal, signed for this computer
            store.meta_set('license_key', answer['key'])
    return True


def every(get_store, health, version):
    """server.py's background loop: a check-in now and every 15 minutes, for as long as it runs."""
    while True:
        try:
            store = get_store()
            checkin(store, health(store), version)
        except Exception:  # noqa: BLE001  (the app keeps running whatever happens here)
            pass
        time.sleep(EVERY_S)
