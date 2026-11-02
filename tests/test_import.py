"""Importing a customer's old gate log from Excel (tools/import_excel.py)."""
import csv
import io
import json
from datetime import datetime, time

from openpyxl import Workbook, load_workbook

from src.store import Store, display, needs_review, to_excel
from tools.import_excel import main

MAPPING = {'columns': {'date': 'Date', 'time': 'Time', 'container': 'Container No', 'plate': 'Truck', 'direction': 'Type'}}


def sample(path):
    wb = Workbook()
    ws = wb.active
    ws.append(['No', 'Date', 'Time', 'Truck', 'Container No', 'Type'])
    ws.append([1, datetime(2024, 3, 12), '08:15', '3231UTA', 'MRSU4425761', 'In'])     # 2: good
    ws.append([2, '13/03/2024', time(9, 0), '', 'MRSU 442576 2', 'خروج'])             # 3: wrong check digit
    ws.append([3, 'yesterday', '10:00', '3231UTA', '', 'IN'])                          # 4: date unreadable
    ws.append([4, '13/03/2024', '11:00', '', '', 'OUT'])                               # 5: nothing to log
    ws.append([5, '13/03/2024', '12:00', '5188VDA', '', 'maybe'])                      # 6: direction unknown
    ws.append([None, None, None, None, None, None])                                    # blank: ignored
    ws.append([7, '14/03/2024 07:30', None, 'أ ب ج 123', 'MSCU1234566', 'OUT'])        # 8: plate kept as typed
    ws.append([8, datetime(2024, 3, 12), '08:15', '3231UTA', 'MRSU4425761', 'IN'])     # 9: same truck again, kept
    wb.save(path)


def run(tmp_path, *extra):
    return main([str(tmp_path / 'old.xlsx'), '--map', str(tmp_path / 'map.json'), '--db', str(tmp_path / 'gate.db'),
                 '--excel-dir', str(tmp_path / 'excel'), '--lang', 'en', *extra])


def test_import_adds_rows_once_and_reports_the_rest(tmp_path):
    sample(tmp_path / 'old.xlsx')
    (tmp_path / 'map.json').write_text(json.dumps(MAPPING), encoding='utf-8')

    added, skipped, problems = run(tmp_path)
    assert (added, skipped) == (4, 0)
    with open(tmp_path / 'old_import_report.csv', encoding='utf-8-sig') as f:
        report = list(csv.DictReader(f))
    assert {r['sheet row'] for r in report if r['result'] == 'NOT ADDED'} == {'4', '5', '6'}  # never dropped silently
    assert any(r['sheet row'] == '3' and 'check digit' in r['problem'] for r in report)
    assert any(r['sheet row'] == '8' and 'plate' in r['problem'] for r in report)

    store = Store(tmp_path / 'gate.db')
    good = store.day('2024-03-12')[0]
    assert (good['time'], good['direction'], good['container'], good['check_digit_ok']) == ('08:15:00', 'IN', 'MRSU 442576 1', 1)
    assert (good['plate'], good['plate_verified'], good['imported']) == ('3231 UTA', 1, 'old.xlsx')
    bad_digit = store.day('2024-03-13')[0]
    assert (bad_digit['direction'], bad_digit['check_digit_ok'], bad_digit['plate']) == ('OUT', 0, None)
    typed = store.day('2024-03-14')[0]
    assert (typed['time'], typed['plate'], typed['plate_verified']) == ('07:30:00', 'أ ب ج 123', 0)

    # marked as imported in Records (the camera column) and in Excel, in both languages
    assert good['camera'] == 'Imported from Excel'
    assert display(good, 'ar')['camera'] == 'مستورد من Excel'
    assert not needs_review(bad_digit)                      # no photos to check; the report lists it
    ws = load_workbook(io.BytesIO(to_excel(store.month('2024-03')))).active
    assert [c.value for c in ws['J']][1:] == ['Imported from Excel'] * 4
    assert load_workbook(tmp_path / 'excel' / 'gate_log_2024-03.xlsx').active.max_row == 5  # rebuilt from the db

    # the same file again adds nothing
    assert run(tmp_path)[:2] == (0, 4)
    assert len(store.month('2024-03')) == 4
