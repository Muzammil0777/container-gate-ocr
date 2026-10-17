"""Scanner on a real frame: a full scan, then follow frames that re-read the same code."""
from pathlib import Path

import cv2
import numpy as np

from src.recognizer import Recognizer
from src.scanner import Scanner

ROOT = Path(__file__).resolve().parent.parent


def test_full_scan_then_follow_the_truck_as_it_moves():
    img = cv2.imread(str(ROOT / 'images/ksa_mrsu_3231uta.jpg'))
    img = cv2.copyMakeBorder(cv2.resize(img, None, fx=1.35, fy=1.35), 0, 0, 0, 2626, cv2.BORDER_REPLICATE)  # 4K camera
    s = Scanner(Recognizer(), full_every_s=1.5)
    first = s(img, 0)
    assert first['mode'] == 'full' and [c['code'] for c in first['codes']] == ['MRSU4425761']
    for i, now in enumerate((0.3, 0.6, 0.9), 1):
        moved = np.roll(img, (6 * i, 9 * i), axis=(0, 1))  # the truck moves a little each frame
        out = s(moved, now)
        assert out['mode'] == 'follow', now
        assert [c['code'] for c in out['codes']] == ['MRSU4425761'], now
        assert [p['plate'] for p in out['plates']] == ['3231 UTA'], now
        assert out['ms'] < first['ms'] * 0.9                      # cheaper than a full scan
    assert s(img, 1.6)['mode'] == 'full'                           # periodic full scan


def test_nothing_found_keeps_full_scanning():
    s = Scanner(Recognizer())
    blank = np.full((400, 600, 3), 128, np.uint8)
    assert [s(blank, now)['mode'] for now in (0, 0.2)] == ['full', 'full']
