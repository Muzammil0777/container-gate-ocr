import numpy as np
from openpyxl import load_workbook

from src.gate import ExcelLog, GateTracker

FRAME = np.zeros((100, 200, 3), np.uint8)


def code(c, valid=True, score=0.9):
    return {'code': c, 'valid': valid, 'size_type': '45G1', 'score': score, 'box': (10, 10, 50, 20)}


def plate(digits='3231', letters='UTA', verified=True, score=0.9):
    return {'plate': f'{digits} {letters}', 'digits': digits, 'letters': letters, 'arabic': 'و ط ا ٣٢٣١',
            'verified': verified, 'score': score, 'box': (20, 60, 40, 20)}


def run(tracker, frames):
    """frames: [(now, codes, plates)] -> [(now, event)]"""
    return [(now, e) for now, cs, ps in frames for e in tracker.update(cs, FRAME, now, ps)]


def test_plate_and_container_make_one_event():
    t = GateTracker(min_hits=2)
    events = run(t, [(0, [code('MRSU4425761')], [plate()]),
                     (1, [code('MRSU4425761', score=0.95)], [plate()]),
                     (2, [code('MRSU4425761')], [plate()])])        # truck still in view
    assert len(events) == 1
    now, e = events[0]
    assert now == 1 and e['code']['code'] == 'MRSU4425761' and e['plate']['plate'] == '3231 UTA'
    assert e['code']['score'] == 0.95                                # best read is kept


def test_container_only_truck_is_logged_after_gap():
    t = GateTracker(min_hits=2, gap_s=5)
    events = run(t, [(0, [code('TRLU6689574')], []), (1, [code('TRLU6689574')], []),
                     (3, [], []), (7, [], [])])
    assert [(now, e['code']['code'], e['plate']) for now, e in events] == [(7, 'TRLU6689574', None)]


def test_plate_only_truck_after_max_wait():
    t = GateTracker(min_hits=2, max_wait_s=10)
    frames = [(s, [], [plate('5188', 'VDA')]) for s in range(12)]
    assert [now for now, _ in run(t, frames)] == [11]               # first confirmed at 1, +10 s


def test_cooldown_then_next_truck():
    t = GateTracker(min_hits=2, cooldown_s=60)
    first = run(t, [(0, [code('TRLU6689574')], [plate()]), (1, [code('TRLU6689574')], [plate()])])
    parked = run(t, [(s, [code('TRLU6689574')], [plate()]) for s in range(2, 30)])
    nxt = run(t, [(30, [code('TCNU6345807')], [plate('5489', 'EXA')]),
                  (31, [code('TCNU6345807')], [plate('5489', 'EXA')])])
    assert len(first) == 1 and parked == []
    assert [(e['code']['code'], e['plate']['plate']) for _, e in nxt] == [('TCNU6345807', '5489 EXA')]


def test_unverified_needs_double_votes():
    t = GateTracker(min_hits=2, gap_s=100, max_wait_s=100)
    assert run(t, [(i, [code('TCNU634580?', valid=False)], [plate(verified=False)]) for i in range(3)]) == []
    assert len(run(t, [(3, [code('TCNU634580?', valid=False)], [plate(verified=False)])])) == 1
    strict = GateTracker(min_hits=2, accept_unverified=False)
    assert run(strict, [(i, [code('TCNU634580?', valid=False)], []) for i in range(9)]) == []


def test_flush_emits_visit_in_progress():
    t = GateTracker(min_hits=2)
    run(t, [(0, [code('TRLU6689574')], []), (1, [code('TRLU6689574')], [])])
    assert [e['code']['code'] for e in t.flush(2)] == ['TRLU6689574']


def event(c=None, p=None):
    return {'code': c, 'plate': p, 'frame': FRAME, 'plate_frame': FRAME if p else None}


def test_excel_log_english(tmp_path):
    log = ExcelLog(str(tmp_path / 'gate_%Y.xlsx'), tmp_path / 'snaps')
    log.log(event(code('TRLU6689574'), plate()), camera='Gate 1', location='North', direction='IN')
    log.log(event(code('TCNU6345807')), camera='Gate 1', location='North', direction='OUT')
    rows = list(load_workbook(next(tmp_path.glob('gate_*.xlsx'))).active.values)
    assert rows[0][:7] == ('Date', 'Time', 'Direction', 'Plate', 'Plate (Arabic)', 'Plate Check', 'Container Code')
    assert rows[1][2:9] == ('IN', '3231 UTA', 'و ط ا ٣٢٣١', 'Arabic + Latin match', 'TRLU 668957 4', 'YES', '45G1')
    assert rows[1][12:] == ('open image', 'open image')
    assert rows[2][2:4] == ('OUT', None) and rows[2][13] is None   # no plate on this truck
    assert len(list((tmp_path / 'snaps').rglob('*.jpg'))) == 3      # 2 snapshots + 1 plate crop


def test_excel_log_arabic_and_column_mismatch(tmp_path):
    path = str(tmp_path / 'gate.xlsx')
    ExcelLog(path, tmp_path / 's').log(event(code('TRLU6689574')), direction='IN')       # English file
    ExcelLog(path, tmp_path / 's', language='ar').log(event(None, plate()), direction='IN')
    ar = load_workbook(tmp_path / 'gate_2.xlsx').active                                  # new file, not mixed
    rows = list(ar.values)
    assert ar.sheet_view.rightToLeft and rows[0][:3] == ('التاريخ', 'الوقت', 'الاتجاه')
    assert rows[1][2:6] == ('دخول', '3231 UTA', 'و ط ا ٣٢٣١', 'مطابق عربي ولاتيني')
    assert len(list(load_workbook(path).active.values)) == 2                             # English untouched


def test_excel_locked_rows_are_queued_not_lost(tmp_path, monkeypatch):
    import openpyxl.workbook.workbook as wbmod
    log = ExcelLog(str(tmp_path / 'gate.xlsx'), tmp_path / 'snaps')
    real_save = wbmod.Workbook.save
    monkeypatch.setattr(wbmod.Workbook, 'save', lambda *a: (_ for _ in ()).throw(PermissionError))
    log.log(event(code('TRLU6689574')))
    assert len(log.pending) == 1
    monkeypatch.setattr(wbmod.Workbook, 'save', real_save)
    log.log(event(code('TCNU6345807')))
    assert log.pending == [] and len(list(load_workbook(tmp_path / 'gate.xlsx').active.values)) == 3


def test_excel_dedupe_and_merge(tmp_path):
    from datetime import datetime, timedelta
    path, t0 = str(tmp_path / 'gate.xlsx'), datetime(2026, 10, 15, 9, 0, 0)
    log = ExcelLog(path, tmp_path / 's', dedupe_s=300)
    first = log.log(event(code('MRSU4425761')), direction='IN', when=t0)                       # container only
    merged = log.log(event(code('MRSU4425761'), plate()), direction='IN', when=t0 + timedelta(seconds=40))
    dup = log.log(event(None, plate()), direction='IN', when=t0 + timedelta(seconds=90))        # same truck again
    out = log.log(event(code('MRSU4425761'), plate()), direction='OUT', when=t0 + timedelta(seconds=120))
    later = log.log(event(code('MRSU4425761'), plate()), direction='IN', when=t0 + timedelta(minutes=30))
    # restart: a new ExcelLog still sees the workbook's recent rows
    again = ExcelLog(path, tmp_path / 's').log(event(code('MRSU4425761')), direction='IN',
                                               when=t0 + timedelta(minutes=31))
    assert [r['status'] for r in (first, merged, dup, out, later, again)] == \
        ['added', 'merged', 'duplicate', 'added', 'added', 'duplicate']
    rows = list(load_workbook(path).active.values)[1:]
    assert [(r[2], r[3], r[6]) for r in rows] == [('IN', '3231 UTA', 'MRSU 442576 1'), ('OUT', '3231 UTA', 'MRSU 442576 1'),
                                                  ('IN', '3231 UTA', 'MRSU 442576 1')]
    assert rows[0][13] == 'open image'                                  # plate image link filled in by the merge
    snaps = [p.name for p in (tmp_path / 's').rglob('*.jpg')]
    assert len(snaps) == 3 + 1 + 2                                      # 3 row snapshots + merged plate + 2 plate images


def test_unverified_container_upgraded_by_valid_read(tmp_path):
    from datetime import datetime, timedelta
    path, t0 = str(tmp_path / 'gate.xlsx'), datetime(2026, 10, 15, 9, 0, 0)
    log = ExcelLog(path, tmp_path / 's')
    log.log(event(code('MRSU442576?', valid=False), plate()), direction='IN', when=t0)
    r = log.log(event(code('MRSU4425761')), direction='IN', when=t0 + timedelta(seconds=30))
    rows = list(load_workbook(path).active.values)[1:]
    assert r['status'] == 'merged' and [(x[6], x[7]) for x in rows] == [('MRSU 442576 1', 'YES')]


def test_read_and_export_one_day(tmp_path):
    import io
    from datetime import datetime
    from src.gate import export_day, read_day
    log = ExcelLog(str(tmp_path / 'logs' / 'gate_%Y-%m.xlsx'), tmp_path / 's')
    log.log(event(code('TRLU6689574'), plate()), direction='IN', when=datetime(2026, 10, 14, 23, 59, 0))
    log.log(event(code('MRSU4425761'), plate('5489', 'EXA')), direction='IN', when=datetime(2026, 10, 15, 8, 0, 0))
    log.log(event(None, plate('5188', 'VDA')), direction='OUT', when=datetime(2026, 10, 15, 9, 30, 0))
    rows = read_day(tmp_path / 'logs', '2026-10-15')
    assert [(r['time'], r['plate'], r['container']) for r in rows] == \
        [('08:00:00', '5489 EXA', 'MRSU 442576 1'), ('09:30:00', '5188 VDA', None)]
    assert rows[0]['snapshot'].endswith('.jpg')                       # link target kept
    wb = load_workbook(io.BytesIO(export_day(rows, 'ar')))
    out = list(wb.active.values)
    assert out[0][0] == 'التاريخ' and len(out) == 3 and out[1][3] == '5489 EXA'
    assert wb.active.cell(row=2, column=13).hyperlink.target == rows[0]['snapshot']
    assert read_day(tmp_path / 'logs', '2026-10-16') == []
