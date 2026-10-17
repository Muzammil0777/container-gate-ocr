"""Search the whole frame, then follow what was found.

A full-frame read of a 4K camera takes about a second, mostly spent *finding* text in a big
picture. A truck is readable for only a few seconds, so after a full scan finds a container
code or plate, the next frames only search small windows around where they were last seen
(enlarged, because the truck moves, grows and turns as it approaches). Searching a small
window at its own size is several times cheaper, so the truck gets many more reads while it
is readable. A full scan runs again every `full_every_s`, or when the windows go empty.
"""
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR


class Scanner:
    def __init__(self, recognizer, full_every_s=3.0, margin=0.6, min_margin=320, misses=2, det_side=1280):
        self.rec, self.full_every_s, self.det_side = recognizer, full_every_s, det_side
        self.margin, self.min_margin, self.misses = margin, min_margin, misses
        # text detection that never enlarges a window (RapidOCR's default scales every image up
        # to 736 px on its short side); windows are searched at most det_side px wide
        self.det = RapidOCR(det_limit_side_len=960, det_limit_type='max')
        self.areas = []         # [{'box': (x, y, w, h), 'miss': int}]
        self.last_full = -1e9

    def __call__(self, frame, now, **opts):
        """Recognizer output for this frame (boxes in frame pixels), plus 'mode' ('full' or
        'follow')."""
        if self.areas and now - self.last_full < self.full_every_s:
            out = self._follow(frame, opts)
            if out is not None:
                return out
        out = self.rec(frame, **opts)
        self.last_full, out['mode'] = now, 'full'
        self.areas = [{'box': b, 'miss': 0} for b in _merge([c['box'] for c in out['codes']] +
                                                            [p['box'] for p in out['plates']])]
        return out

    def _follow(self, frame, opts):
        """Search and read only the windows; None when they have all gone empty."""
        t0 = cv2.getTickCount()
        H, W = frame.shape[:2]
        items, kept = [], []
        for a in self.areas:
            x, y, w, h = a['box']
            m = self.min_margin + int(max(w, h) * self.margin)  # how far the truck may move between looks
            x0, y0, x1, y1 = max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m)
            win = frame[y0:y1, x0:x1]
            f = min(1.0, self.det_side / max(win.shape[:2]))  # search small, read sharp
            small = cv2.resize(win, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else win
            boxes, _ = self.det(small, use_cls=False, use_rec=False)
            found = []
            if boxes:
                pts = [np.array(b, dtype=np.float32) / f for b in boxes]
                rec, _ = self.rec.engine.text_rec(self.rec.engine.get_crop_img_list(win, pts))
                for p, r in zip(pts, rec):
                    if r[1] >= self.rec.engine.text_score:
                        bx, by, bw, bh = cv2.boundingRect(p.astype(np.int32))
                        found.append((r[0], float(r[1]), (x0 + bx, y0 + by, bw, bh)))
            for text, score, (bx, by, bw, bh) in list(found):
                if bh > 2.5 * bw:  # vertical side code: unstack and read as one line
                    item = self.rec._reread_column(frame, (bx, by, bw, bh), bh // 2)
                    if item:
                        found.append(item)
            items += found
            a['miss'] = 0 if found else a['miss'] + 1
            if a['miss'] < self.misses:
                kept.append(a)
        out = self.rec._codes(items)
        for c in out['codes']:
            if c['code'].endswith('?'):
                self.rec._read_check_digit(frame, c, items)
        plates = self.rec._plates(frame, items, fallback=False) if opts.get('plates', True) else []
        out['plates'] = [p for p in plates if not any(_overlaps(p['latin_box'], c['box']) for c in out['codes'])]
        del out['items']
        # move the windows to where the code / plate is now
        hits = [c['box'] for c in out['codes']] + [p['box'] for p in out['plates']]
        for a in kept:
            reach = _grow(a['box'], self.min_margin + int(max(a['box'][2:]) * self.margin))
            near = [b for b in hits if _overlaps(b, reach)]
            if near:
                a['box'] = _merge(near)[0]
        self.areas = kept
        if not self.areas:
            return None
        out['ms'] = round((cv2.getTickCount() - t0) / cv2.getTickFrequency() * 1000)
        out['mode'] = 'follow'
        return out


def _grow(box, px):
    x, y, w, h = box
    return x - px, y - px, w + 2 * px, h + 2 * px


def _overlaps(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _merge(boxes):
    """Merge overlapping / nearby boxes (a container code's lines, or a plate) into one."""
    boxes = [list(b) for b in boxes]
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if _overlaps(_grow(boxes[i], 40), boxes[j]):
                    a, b = boxes[i], boxes.pop(j)
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    boxes[i] = [x0, y0, max(a[0] + a[2], b[0] + b[2]) - x0, max(a[1] + a[3], b[1] + b[3]) - y0]
                    merged = True
                    break
            if merged:
                break
    return [tuple(b) for b in boxes]
