"""Accuracy regression on images/. Slow (~15 s, loads the OCR models).
Misses still to fix: code4, code5_fix, code6, face2 (blurry / partial vertical codes);
code2_fix reads without its check digit."""
from pathlib import Path

import cv2
import pytest

from src.recognizer import Recognizer

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = {  # image: best code; '?' = check digit not readable in that image
    'images/code1.png': 'YMMU6124942',
    'images/code2.png': 'TRLU6689574',
    'images/code2_fix.png': 'TRLU668957?',
    'images/code2_prerotate.png': 'TRLU6689574',
    'images/code2_rotated.png': 'TRLU6689574',
    'images/code3.png': 'COLU2008412',
    'images/container1.png': 'TRLU6689574',
    'images/container2.png': 'TCNU6345807',
    'images/container3.png': 'TRLU6689574',
    'images/container4.png': 'BCHU2970249',
    'images/face3.png': 'YMMU6124942',
    'images/face4.png': 'TRLU6689574',
    'images/ocr_test.png': 'BBUU2040344',
    'images/side_vertical_ffau.jpg': 'FFAU2160058',   # stacked side code, needs vertical pass
    'demo_input.jpg': 'YMMU6124942',
}


@pytest.fixture(scope='module')
def recognizer():
    return Recognizer()


@pytest.mark.parametrize('path,code', EXPECTED.items())
def test_sample(recognizer, path, code):
    codes = recognizer(cv2.imread(str(ROOT / path)))['codes']
    assert [c['code'] for c in codes] == [code]
