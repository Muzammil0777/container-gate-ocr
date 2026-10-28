"""Accuracy regression on images/. Slow (~15 s, loads the OCR models).
Misses still to fix: code4, code5_fix, code6, face2 (blurry / partial vertical codes);
the boxed check digit is recovered by a targeted read."""
from pathlib import Path

import cv2
import pytest

from src.recognizer import Recognizer

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = {  # image: best code; '?' = check digit not readable in that image
    'images/code1.png': 'YMMU6124942',
    'images/code2.png': 'TRLU6689574',
    'images/code2_fix.png': 'TRLU6689574',
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
    'images/ksa_ffau_5489exa.jpg': 'FFAU2160058',
    'images/ksa_mrsu_3231uta.jpg': 'MRSU4425761',
    'images/ksa_ecmu_5188vda.jpg': 'ECMU5468326',
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


PLATES = {  # Saudi plates: Latin reading, confirmed by the Arabic row
    'images/ksa_ffau_5489exa.jpg': '5489 EXA',
    'images/ksa_mrsu_3231uta.jpg': '3231 UTA',
    'images/ksa_ecmu_5188vda.jpg': '5188 VDA',
}


@pytest.mark.parametrize('path,plate', PLATES.items())
def test_plate(recognizer, path, plate):
    plates = recognizer(cv2.imread(str(ROOT / path)))['plates']
    assert [(p['plate'], p['verified']) for p in plates] == [(plate, True)]


def test_door_markings_are_not_plates(recognizer):
    # 2.5K yard camera: '764 CU.M' and '61490 LBS' (white paint on the door) were read as
    # plates '764 GLN' and '1499 LBS'; the container itself must still be read
    out = recognizer(cv2.imread(str(ROOT / 'tests/data/yard_door_weights.jpg')))
    assert [c['code'] for c in out['codes']] == ['CAAU9873210']
    assert out['plates'] == []


def test_no_verified_plate_on_container_only_images(recognizer):
    for path in EXPECTED:
        if path not in PLATES:
            assert not any(p['verified'] for p in recognizer(cv2.imread(str(ROOT / path)))['plates']), path
