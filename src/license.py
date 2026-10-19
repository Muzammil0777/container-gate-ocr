"""License keys: signed by the vendor, checked offline on the gate computer.

A key is a short text, GATE1.<details>.<signature>: the details (customer, site, the
computer's machine code, end date, ...) signed with the vendor's Ed25519 private key. The app
holds only public keys (PUBLIC_KEYS), so it can check a key but nobody can make one without
the private key, which never leaves the vendor (tools/license_tool.py).

States: trial (14 days from the first start, no key needed), active, expiring (from 30 days
before the end date), grace (14 days after it), then expired; unlicensed after a trial with
no key. Detection runs in trial, active, expiring and grace; records and exports always work.
The latest time seen is kept, so setting the computer's clock back doesn't extend anything.
"""
import base64
import binascii
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PREFIX = 'GATE1'
TRIAL_DAYS, WARN_DAYS, GRACE_DAYS = 14, 30, 14
PUBLIC_KEYS = {}  # key id -> Ed25519 public key (hex); the real one is added with tools/license_tool.py keygen


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text):
    return base64.b64decode(text + '=' * (-len(text) % 4), altchars=b'-_', validate=True)


def machine_code(guid=None):
    """This computer's code, e.g. 'K3QF-7ZPA-M2XD': from Windows' machine ID, which stays the
    same when the app is reinstalled and changes with the computer."""
    if guid is None:
        guid = _machine_guid()
    code = base64.b32encode(hashlib.sha256(f'container-gate-ocr:{guid}'.encode()).digest()).decode()[:12]
    return '-'.join(code[i:i + 4] for i in (0, 4, 8))


def _machine_guid():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            return winreg.QueryValueEx(k, 'MachineGuid')[0]
    except (ImportError, OSError):  # not Windows
        return str(uuid.getnode())


def make_key(payload, private_key, kid):
    """A license key for payload (dict with at least machine and expires 'YYYY-MM-DD'), signed
    with the raw 32-byte Ed25519 private key `private_key` known by key id `kid`."""
    body = json.dumps({**payload, 'kid': kid}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    sig = Ed25519PrivateKey.from_private_bytes(private_key).sign(body)
    return f'{PREFIX}.{_b64(body)}.{_b64(sig)}'


def read_key(text, keys=None, machine=None):
    """(details, None) for a genuine key made for this computer, else (None, text key of the
    reason). Spaces and line breaks from copying are ignored."""
    keys = PUBLIC_KEYS if keys is None else keys
    try:
        prefix, body_b64, sig_b64 = ''.join(text.split()).split('.')
        if prefix != PREFIX:
            raise ValueError(prefix)
        body, sig = _unb64(body_b64), _unb64(sig_b64)
        payload = json.loads(body)
        date.fromisoformat(payload['expires'])
        kid = payload['kid']
    except (ValueError, KeyError, TypeError, AttributeError, binascii.Error):
        return None, 'license_bad_format'
    if kid not in keys:
        return None, 'license_unknown_signer'
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys[kid])).verify(sig, body)
    except (InvalidSignature, ValueError):
        return None, 'license_bad_signature'
    if payload.get('machine') != (machine or machine_code()):
        return None, 'license_other_machine'
    return payload, None


def status(payload, first_start, today):
    """{'state', 'ends' (date), 'days_left'} for a license's details (None: no valid key, so the
    trial from first_start) on `today`. days_left is negative after the end date."""
    if payload is None:
        ends = first_start + timedelta(days=TRIAL_DAYS)
        left = (ends - today).days
        return {'state': 'trial' if left > 0 else 'unlicensed', 'ends': ends.isoformat(), 'days_left': left}
    ends = date.fromisoformat(payload['expires'])
    left = (ends - today).days
    state = ('active' if left > WARN_DAYS else 'expiring' if left >= 0
             else 'grace' if left >= -GRACE_DAYS else 'expired')
    return {'state': state, 'ends': ends.isoformat(), 'days_left': left}


def detection_allowed(state):
    return state in ('trial', 'active', 'expiring', 'grace')


def _when(text):
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def check(store, machine=None, keys=None, now=None):
    """The license state of this computer, from the key, trial start and latest time seen kept
    in the gate database (store). Also records the time, for the clock guard."""
    now = now or datetime.now()
    last = _when(store.meta_get('last_seen'))
    effective = max(now, last) if last else now
    if last is None or now > last:
        store.meta_set('last_seen', now.isoformat(timespec='seconds'))
    first = _when(store.meta_get('first_start'))
    if first is None:
        first = effective
        store.meta_set('first_start', first.isoformat(timespec='seconds'))
    machine = machine or machine_code()
    text = store.meta_get('license_key')
    payload, error = read_key(text, keys, machine) if text else (None, None)
    return {**status(payload, first.date(), effective.date()), 'machine': machine, 'key_error': error,
            'clock_behind': last is not None and now < last - timedelta(days=1),
            **{k: (payload or {}).get(k) for k in ('customer', 'site', 'lid', 'cameras')}}
