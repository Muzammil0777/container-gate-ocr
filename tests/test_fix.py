"""Corrections typed by a person in the app: checking them, and saving them everywhere."""
import json

import src.config
from src.store import Store, parse_fix


def test_parse_fix_good_plate_and_container():
    fix, errors = parse_fix('3231 uta', 'mrsu442576 1', 'OUT')
    assert errors == []
    assert fix['direction'] == 'OUT'
    assert (fix['plate'], fix['plate_verified']) == ('3231 UTA', 1) and fix['plate_ar']
    assert (fix['container'], fix['check_digit_ok']) == ('MRSU 442576 1', 1)


def test_parse_fix_wrong_check_digit_is_saved_but_flagged():
    fix, errors = parse_fix('', 'MRSU 442576 2', 'IN')
    assert errors == [] and fix['check_digit_ok'] == 0


def test_parse_fix_bad_input():
    assert parse_fix('hello', 'MRSU 4425', 'IN')[1] == ['bad_plate', 'bad_container']


def test_parse_fix_empty_clears_readings():
    fix, errors = parse_fix(' ', '', 'IN')
    assert errors == []
    assert fix == {'direction': 'IN', 'plate': None, 'plate_ar': None, 'plate_verified': None,
                   'container': None, 'check_digit_ok': None, 'size_type': None}


def test_save_fix_updates_db_excel_and_log(tmp_path, monkeypatch):
    monkeypatch.setattr(src.config, 'ROOT', tmp_path)
    monkeypatch.setattr(src.config, 'CONFIG', tmp_path / 'cameras.json')
    store = Store(str(tmp_path / 'gate.db'))
    _, rid = store.add({'date': '2026-10-17', 'time': '10:00:00', 'direction': 'IN', 'plate': '231 UTA'})
    row = store.get(rid)
    fix, _ = parse_fix('3231 UTA', '', 'IN')
    src.config.save_fix(store, row, fix)
    assert store.get(rid)['plate'] == '3231 UTA' and store.get(rid)['corrected'] == 1
    assert sorted(p.name for p in (tmp_path / 'logs' / 'excel').iterdir()) == \
        ['gate_log_2026-10-17.xlsx', 'gate_log_2026-10.xlsx']
    entry = json.loads((tmp_path / 'logs' / 'corrections.jsonl').read_text(encoding='utf-8'))
    assert entry['before']['plate'] == '231 UTA' and entry['after']['plate'] == '3231 UTA'
