"""Named users (logs/gate.db) and the upgrade from the single site password."""
import sqlite3
from contextlib import closing

import pytest

import server
from src import config
from src.store import Store
from tests.test_store import OLD_SCHEMA


@pytest.fixture
def old_site(tmp_path, monkeypatch):
    """A site saved by the version before named users: site password in cameras.json, a
    gate.db with only the trucks table and one row."""
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setattr(config, 'CONFIG', tmp_path / 'cameras.json')
    old_hash = server.hash_password('gate1234')
    config.save_config({'cameras': [{'name': 'Gate 1'}], 'site_password': old_hash, 'session_secret': 'ab' * 32})
    (tmp_path / 'logs').mkdir()
    with closing(sqlite3.connect(tmp_path / 'logs' / 'gate.db')) as db, db:
        db.executescript(OLD_SCHEMA)
        db.execute("INSERT INTO trucks (date, time, direction, plate) VALUES ('2026-10-18', '08:00:00', 'IN', '5188 VDA')")
    server.get_store.cache_clear()
    yield tmp_path, old_hash
    server.get_store.cache_clear()


def test_old_site_password_becomes_user_admin(old_site):
    tmp_path, old_hash = old_site
    before = config.CONFIG.read_text(encoding='utf-8')
    store = server.get_store()
    admin = store.user('admin')
    assert admin['role'] == 'admin' and admin['active'] == 1 and admin['password_hash'] == old_hash
    assert server.check_password('gate1234', admin['password_hash'])
    assert [r['plate'] for r in store.day('2026-10-18')] == ['5188 VDA']          # records kept
    assert config.CONFIG.read_text(encoding='utf-8') == before                    # settings untouched
    assert b'gate1234' not in (tmp_path / 'logs' / 'gate.db').read_bytes()


def test_upgrade_runs_once(old_site):
    store = server.get_store()
    server.users_from_site_password(store, config.load_config())                # next start: already has users
    assert store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1


def test_new_site_without_password_has_no_users(tmp_path):
    store = Store(str(tmp_path / 'gate.db'))
    server.users_from_site_password(store, {})
    assert not store.has_users()


def test_usernames_unique_in_any_case(tmp_path):
    store = Store(str(tmp_path / 'gate.db'))
    uid = store.add_user(' Ahmed ', server.hash_password('pw123456'), 'operator', name='Ahmed Ali')
    assert store.user('AHMED')['id'] == uid and store.user(uid=uid)['username'] == 'Ahmed'
    with pytest.raises(sqlite3.IntegrityError):
        store.add_user('ahmed', server.hash_password('other123'), 'viewer')
    with pytest.raises(sqlite3.IntegrityError):
        store.add_user('sara', server.hash_password('other123'), 'boss')            # no such role
    with pytest.raises(ValueError):
        store.add_user('sara', 'plain password', 'viewer')                          # never a plain password
    assert store.user('nobody') is None
    store.set_user_password(uid, server.hash_password('new12345'))
    assert server.check_password('new12345', store.user(uid=uid)['password_hash'])
    with pytest.raises(ValueError):
        store.set_user_password(uid, 'new12345')
