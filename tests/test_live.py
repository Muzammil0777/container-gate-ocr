"""LiveManager (the app's Live tab runner) on a short video standing in for a camera. Slow (~15 s)."""
import time
from pathlib import Path

import cv2
import numpy as np
from cctv import LiveManager

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
