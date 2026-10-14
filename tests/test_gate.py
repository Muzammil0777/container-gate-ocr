import numpy as np
from openpyxl import load_workbook

from src.gate import ExcelLog, GateTracker

FRAME = np.zeros((100, 200, 3), np.uint8)


def code(c, valid=True, score=0.9):
    return {'code': c, 'valid': valid, 'size_type': '45G1', 'score': score, 'box': (10, 10, 50, 20)}


def test_tracker_votes_then_cools_down():
    t = GateTracker(min_hits=2, window_s=10, cooldown_s=60)
    assert t.update([code('TRLU6689574')], FRAME, now=0) == []
    events = t.update([code('TRLU6689574', score=0.95)], FRAME, now=1)
    assert [e[0]['score'] for e in events] == [0.95]       # best read is kept
    assert t.update([code('TRLU6689574')] * 2, FRAME, now=5) == []   # truck still there
    assert t.update([code('TRLU6689574')], FRAME, now=100) == []     # back: needs votes again
    assert len(t.update([code('TRLU6689574')], FRAME, now=101)) == 1


def test_tracker_hits_expire():
    t = GateTracker(min_hits=2, window_s=10)
    t.update([code('TRLU6689574')], FRAME, now=0)
    assert t.update([code('TRLU6689574')], FRAME, now=20) == []      # too far apart


def test_tracker_unverified_needs_double_votes():
    t = GateTracker(min_hits=2)
    seen = [t.update([code('TCNU634580?', valid=False)], FRAME, now=i) for i in range(4)]
    assert [len(e) for e in seen] == [0, 0, 0, 1]
    strict = GateTracker(min_hits=2, accept_unverified=False)
    assert all(strict.update([code('TCNU634580?', valid=False)], FRAME, now=i) == [] for i in range(9))


def test_excel_log(tmp_path):
    log = ExcelLog(str(tmp_path / 'gate_%Y.xlsx'), tmp_path / 'snaps')
    log.log(code('TRLU6689574'), FRAME, camera='Gate 1', location='North', direction='IN')
    row = log.log(code('TCNU6345807'), FRAME, camera='Gate 1', location='North', direction='OUT')
    ws = load_workbook(next(tmp_path.glob('gate_*.xlsx'))).active
    rows = list(ws.values)
    assert rows[1][2:8] == ('TRLU 668957 4', 'YES', '45G1', 'IN', 'Gate 1', 'North')
    assert rows[2][5] == 'OUT' and len(rows) == 3
    assert len(list((tmp_path / 'snaps').rglob('*.jpg'))) == 2 and row['Snapshot'].endswith('.jpg')


def test_excel_locked_rows_are_queued_not_lost(tmp_path, monkeypatch):
    import openpyxl.workbook.workbook as wbmod
    log = ExcelLog(str(tmp_path / 'gate.xlsx'), tmp_path / 'snaps')
    real_save = wbmod.Workbook.save
    monkeypatch.setattr(wbmod.Workbook, 'save', lambda *a: (_ for _ in ()).throw(PermissionError))
    log.log(code('TRLU6689574'), FRAME)
    assert len(log.pending) == 1
    monkeypatch.setattr(wbmod.Workbook, 'save', real_save)
    log.log(code('TCNU6345807'), FRAME)
    assert log.pending == [] and len(list(load_workbook(tmp_path / 'gate.xlsx').active.values)) == 3
