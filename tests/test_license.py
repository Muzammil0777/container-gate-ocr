"""License keys: signed by the vendor, checked offline on the gate computer."""
from datetime import date, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src import license as lic
from src.store import Store

PRIVATE = Ed25519PrivateKey.generate()  # a test-only signing key, never the real one
RAW_PRIVATE = PRIVATE.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                    serialization.NoEncryption())
KEYS = {'t1': PRIVATE.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()}
HERE = lic.machine_code('11111111-2222-3333-4444-555555555555')
ELSEWHERE = lic.machine_code('99999999-2222-3333-4444-555555555555')


def key(machine=HERE, expires='2027-10-19', kid='t1', private=RAW_PRIVATE, **extra):
    return lic.make_key({'lid': 'L-0001', 'customer': 'Port Co', 'site': 'Jeddah gate', 'machine': machine,
                         'issued': '2026-10-19', 'expires': expires, **extra}, private, kid)


def test_machine_code_is_stable_short_and_differs_per_computer():
    assert HERE == lic.machine_code('11111111-2222-3333-4444-555555555555')
    assert HERE != ELSEWHERE
    assert len(HERE) == 14 and HERE.count('-') == 2 and HERE.replace('-', '').isalnum()
    assert len(lic.machine_code()) == 14  # this computer


def test_a_key_issued_for_this_computer_is_accepted():
    payload, error = lic.read_key(key(), KEYS, HERE)
    assert error is None and payload['customer'] == 'Port Co' and payload['expires'] == '2027-10-19'


def test_pasted_keys_may_carry_spaces_and_line_breaks():
    k = key()
    messy = '  ' + k[:20] + '\n' + k[20:40] + ' \r\n' + k[40:] + '\n'
    assert lic.read_key(messy, KEYS, HERE)[1] is None


def test_changed_keys_and_other_computers_are_refused():
    k = key()
    body, sig = k.split('.')[1:]
    tampered = k.replace(body, body[:-2] + ('A' if body[-2] != 'A' else 'B') + body[-1])
    assert lic.read_key(tampered, KEYS, HERE)[1] in ('license_bad_signature', 'license_bad_format')
    assert lic.read_key(key(expires='2099-12-31')[:-4] + sig[-4:], KEYS, HERE)[1] == 'license_bad_signature'
    assert lic.read_key(key(machine=ELSEWHERE), KEYS, HERE) == (None, 'license_other_machine')
    assert lic.read_key(key(kid='other'), KEYS, HERE) == (None, 'license_unknown_signer')
    other_signer = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    assert lic.read_key(key(private=other_signer), KEYS, HERE) == (None, 'license_bad_signature')
    for junk in ('', 'hello', 'GATE1.abc', 'GATE1.!!!.???', 'GATE2.' + k[6:]):
        assert lic.read_key(junk, KEYS, HERE) == (None, 'license_bad_format'), junk


@pytest.mark.parametrize('today, state, days_left', [
    ('2027-09-18', 'active', 31),
    ('2027-09-19', 'expiring', 30),     # banner from 30 days before
    ('2027-10-19', 'expiring', 0),      # the last day still counts
    ('2027-10-20', 'grace', -1),        # 14 days of grace
    ('2027-11-02', 'grace', -14),
    ('2027-11-03', 'expired', -15),
])
def test_license_states_by_date(today, state, days_left):
    got = lic.status({'expires': '2027-10-19'}, date(2026, 10, 19), date.fromisoformat(today))
    assert (got['state'], got['days_left'], got['ends']) == (state, days_left, '2027-10-19')


@pytest.mark.parametrize('today, state, days_left', [
    ('2026-10-19', 'trial', 14),
    ('2026-11-01', 'trial', 1),
    ('2026-11-02', 'unlicensed', 0),
    ('2027-01-01', 'unlicensed', -60),
])
def test_trial_without_a_key(today, state, days_left):
    got = lic.status(None, date(2026, 10, 19), date.fromisoformat(today))
    assert (got['state'], got['days_left'], got['ends']) == (state, days_left, '2026-11-02')


def test_detection_runs_in_trial_active_expiring_and_grace_only():
    assert [s for s in ('trial', 'active', 'expiring', 'grace', 'expired', 'unlicensed')
            if lic.detection_allowed(s)] == ['trial', 'active', 'expiring', 'grace']


def test_check_uses_the_stored_key_and_starts_the_trial_once(tmp_path):
    store = Store(str(tmp_path / 'gate.db'))
    now = datetime(2026, 10, 19, 9, 0)
    first = lic.check(store, HERE, KEYS, now)
    assert first['state'] == 'trial' and first['days_left'] == 14 and first['machine'] == HERE
    assert lic.check(store, HERE, KEYS, now + timedelta(days=3))['days_left'] == 11  # trial started on day one
    store.meta_set('license_key', key())
    got = lic.check(store, HERE, KEYS, now + timedelta(days=3))
    assert (got['state'], got['customer'], got['key_error']) == ('active', 'Port Co', None)
    store.meta_set('license_key', key()[:-3] + 'AAA')  # damaged in the database: back to the trial rules
    assert lic.check(store, HERE, KEYS, now + timedelta(days=3))['key_error'] in ('license_bad_signature', 'license_bad_format')


def test_setting_the_clock_back_does_not_extend_anything(tmp_path):
    store = Store(str(tmp_path / 'gate.db'))
    store.meta_set('license_key', key(expires='2026-12-31'))
    late = lic.check(store, HERE, KEYS, datetime(2027, 1, 10, 9, 0))  # 10 days after the end: grace
    assert late['state'] == 'grace'
    back = lic.check(store, HERE, KEYS, datetime(2026, 11, 1, 9, 0))  # clock set back 70 days
    assert back['state'] == 'grace' and back['clock_behind'] is True
    assert lic.check(store, HERE, KEYS, datetime(2027, 2, 1, 9, 0))['state'] == 'expired'
