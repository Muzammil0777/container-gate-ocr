"""LiveManager (the app's Live tab runner) on a short video standing in for a camera. Slow (~15 s)."""
import time
from pathlib import Path

import cv2
import numpy as np
from cctv import LiveManager
from src.lanes import lanes

ROOT = Path(__file__).resolve().parent.parent


def test_live_manager_logs_one_row_per_truck(tmp_path):
    video = tmp_path / 'gate.mp4'
    img = cv2.imread(str(ROOT / 'images/ksa_mrsu_3231uta.jpg'))
    vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 10, (img.shape[1], img.shape[0]))
    for i in range(60):  # 6 s of the same truck, creeping forward
        vw.write(np.roll(img, i // 3, axis=0))
    vw.release()

    m = LiveManager({'db': str(tmp_path / 'gate.db'), 'excel_dir': str(tmp_path / 'excel'),
                     'snapshots': str(tmp_path / 'snaps'), 'live_dir': str(tmp_path / 'live')})
    m.start({'name': 'Gate 1', 'source': str(video), 'direction': 'IN', 'location': 'Test'})
    assert list(m.running()) == ['Gate 1']
    deadline = time.time() + 120
    while m.running() and time.time() < deadline:
        time.sleep(0.5)
    assert (tmp_path / 'live' / 'Gate_1.jpg').exists()
    m.stop('Gate 1')
    assert not (tmp_path / 'live' / 'Gate_1.jpg').exists() and m.running() == {}
    rows = [r for d in sorted({p.parent.name for p in (tmp_path / 'snaps').rglob('*.jpg')}) for r in m.store.day(d)]
    assert [(r['direction'], r['plate'], r['container']) for r in rows] == [('IN', '3231 UTA', 'MRSU 442576 1')]
    m.flush()
    assert len(list((tmp_path / 'excel').glob('gate_log_*.xlsx'))) == 2      # the day's and the month's file


def test_a_lane_of_two_cameras_logs_one_row_verified_by_both(tmp_path):
    """The same truck filmed from two angles; the second camera has a digit hidden at first."""
    img = cv2.imread(str(ROOT / 'images/ksa_mrsu_3231uta.jpg'))
    side = cv2.warpAffine(img, np.float32([[0.85, 0, 60], [0, 0.85, 100]]), (img.shape[1], img.shape[0]))
    rear, angle = tmp_path / 'rear.mp4', tmp_path / 'side.mp4'
    for path, base, hide in ((rear, img, 0), (angle, side, 30)):
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (img.shape[1], img.shape[0]))
        for i in range(60):
            f = np.roll(base, i // 3, axis=0)
            if i < hide:  # something in front of the 5th digit for the first 3 s
                cv2.rectangle(f, (362 + 108, 465 + i // 3), (362 + 124, 515 + i // 3), (128, 128, 128), -1)
            vw.write(f)
        vw.release()

    m = LiveManager({'db': str(tmp_path / 'gate.db'), 'excel_dir': str(tmp_path / 'excel'),
                     'snapshots': str(tmp_path / 'snaps'), 'live_dir': str(tmp_path / 'live')})
    m.start_lane(lanes({'lanes': [{'name': 'Entry', 'direction': 'IN', 'location': 'Gate 1'}],
                        'cameras': [{'name': 'Rear', 'source': str(rear), 'lane': 'Entry', 'role': 'both'},
                                    {'name': 'Side', 'source': str(angle), 'lane': 'Entry', 'role': 'container'}]})[0])
    assert sorted(m.running()) == ['Rear', 'Side']
    deadline = time.time() + 180
    while m.running() and time.time() < deadline:
        time.sleep(0.5)
    assert (tmp_path / 'live' / 'Rear.jpg').exists() and (tmp_path / 'live' / 'Side.jpg').exists()  # Live per camera
    m.stop('Entry')
    rows = [r for d in sorted({p.parent.name for p in (tmp_path / 'snaps').rglob('*.jpg')}) for r in m.store.day(d)]
    assert [(r['lane'], r['direction'], r['plate'], r['container'], r['cams_agree'], r['cams_expected'])
            for r in rows] == [('Entry', 'IN', '3231 UTA', 'MRSU 442576 1', 2, 2)]
    assert Path(rows[0]['snapshot']).exists() and Path(rows[0]['snapshot2']).exists()


def test_reloading_settings_restarts_only_the_lanes_that_changed(tmp_path):
    from cctv import DEFAULTS, reload
    m, calls = LiveManager({'db': str(tmp_path / 'gate.db')}), []
    m.start_lane = lambda ln, nvr, lang: (calls.append(('start', ln['name'])), m.lanes.update({ln['name']: (ln, {'nvr': nvr, 'language': lang}, {})}))
    m.stop = lambda name: (calls.append(('stop', name)), m.lanes.pop(name, None))
    cfg = {**DEFAULTS, 'lanes': [{'name': 'Entry', 'direction': 'IN'}],
           'cameras': [{'name': 'A', 'source': 'a.mp4', 'lane': 'Entry', 'role': 'container'},
                       {'name': 'P', 'source': 'p.mp4', 'lane': 'Entry', 'role': 'plate'},
                       {'name': 'Exit', 'source': 'x.mp4', 'direction': 'OUT'}]}
    reload(m, cfg)
    assert sorted(calls) == [('start', 'Entry'), ('start', 'Exit')]
    calls.clear()
    cfg['cameras'][1] = {**cfg['cameras'][1], 'roi': [0, 0, 0.5, 1]}   # a change in the Entry lane only
    reload(m, cfg)
    assert calls == [('stop', 'Entry'), ('start', 'Entry')]
    calls.clear()
    reload(m, {**cfg, 'cameras': cfg['cameras'][:2]})                   # Exit camera removed
    assert calls == [('stop', 'Exit')]
