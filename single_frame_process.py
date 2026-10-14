"""Read container codes in one image:  python single_frame_process.py -i images/container1.png"""
import argparse

import cv2

from src.iso6346 import format_code
from src.recognizer import Recognizer, draw


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('-i', '--image', default='demo_input.jpg', help='path to input image')
    ap.add_argument('-o', '--output', default='output.jpg', help='where to save the annotated image')
    ap.add_argument('--show', action='store_true', help='display the result in a window')
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        ap.error(f'cannot read image {args.image}')
    out = Recognizer()(img)
    for c in out['codes']:
        status = 'check digit OK' if c['valid'] else 'UNVERIFIED'
        print(f"{format_code(c['code'])}  {c['size_type'] or '':5} {status}  (confidence {c['score']})")
    if not out['codes']:
        print('No container code found.')
    print(f"OCR took {out['ms']} ms")
    cv2.imwrite(args.output, draw(img, out['codes']))
    if args.show:
        cv2.imshow('result', img)
        cv2.waitKey(0)


if __name__ == '__main__':
    main()
