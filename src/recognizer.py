"""Container code + Saudi plate recognition on a whole frame: RapidOCR (PP-OCR, ONNX) +
ISO 6346 and Saudi plate parsing."""
import time
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from src.iso6346 import (TO_DIGIT, _near, check_digit, find_codes, find_size_type, format_code,
                         normalize)
from src.saudi_plate import arabic_matches, format_plate, parse_latin, to_arabic

MODELS = Path(__file__).resolve().parent.parent / 'models'


def unstack(crop):
    """Turn a vertical stack of characters (side codes) into one horizontal line,
    which the recognizer reads far better than sideways text."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    if ink.mean() > 127:  # make text the white minority
        ink = 255 - ink
    rows = list(ink.sum(axis=1) > 0.02 * 255 * ink.shape[1]) + [False]
    segments, start = [], None
    for i, has_ink in enumerate(rows):
        if has_ink and start is None:
            start = i
        elif not has_ink and start is not None:
            if i - start > 0.15 * ink.shape[1]:  # ignore specks
                segments.append((start, i))
            start = None
    if len(segments) < 3:
        return None
    # Characters touching each other ('AU') come out as one double-height segment: split it
    med = sorted(e - s for s, e in segments)[len(segments) // 2]
    split = []
    for s, e in segments:
        n = round((e - s) / med) if e - s > 1.6 * med else 1
        split += [(s + (e - s) * k // n, s + (e - s) * (k + 1) // n) for k in range(n)]
    segments = split
    h = max(e - s for s, e in segments)
    pad = h // 3
    chars = []
    for s, e in segments:
        top = (h - (e - s)) // 2 + pad
        chars.append(cv2.copyMakeBorder(crop[s:e], top, h - (e - s) + 2 * pad - top, pad, pad,
                                        cv2.BORDER_REPLICATE))
    return np.hstack(chars)


def _loose(s):
    """Collapse OCR-confusable characters so 'BB00' matches 'BBUU'."""
    return ''.join(TO_DIGIT.get(c, c) for c in normalize(s))


def _columns(items):
    """Stacked side codes are often detected one character per box: join single-char
    boxes column by column, top to bottom."""
    chars = sorted((it for it in items if len(normalize(it[0])) == 1), key=lambda it: it[2][1])
    columns = []
    for it in chars:
        x, _, w, _ = it[2]
        for col in columns:
            cx, _, cw, _ = col[-1][2]
            if abs((x + w / 2) - (cx + cw / 2)) < max(w, cw):
                col.append(it)
                break
        else:
            columns.append([it])
    joined = []
    for col in (c for c in columns if len(c) >= 4):
        xs = [b[0] for _, _, b in col] + [b[0] + b[2] for _, _, b in col]
        ys = [b[1] for _, _, b in col] + [b[1] + b[3] for _, _, b in col]
        joined.append((''.join(t for t, _, _ in col), min(s for _, s, _ in col),
                       (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))))
    return joined


class Recognizer:
    def __init__(self, max_side=1920, use_cuda=False, sharp=True, vertical_every=1):
        """max_side: frames are downscaled to this to *find* text (speed vs. small far-away text).
        sharp: read each found text box from the full-resolution frame instead of the
        downscaled one (sharper small text from 4K cameras, at almost no extra cost).
        vertical_every: run the (expensive) vertical-code pass only on every Nth call; live
        cameras use 3, since a truck stays in view for several looks anyway.
        use_cuda needs `pip install onnxruntime-gpu` and an NVIDIA GPU."""
        self.max_side, self.sharp = max_side, sharp
        self.vertical_every, self.calls = max(1, vertical_every), 0
        self.engine = RapidOCR(det_use_cuda=use_cuda, rec_use_cuda=use_cuda, cls_use_cuda=use_cuda)
        # Arabic recognition (PP-OCRv5) for the top row of Saudi plates
        self.arabic = RapidOCR(rec_model_path=str(MODELS / 'arabic_PP-OCRv5_rec_mobile.onnx'),
                               rec_keys_path=str(MODELS / 'ppocrv5_arabic_dict.txt'),
                               rec_use_cuda=use_cuda)

    def __call__(self, frame, zoom=True, vertical=True, plates=True, max_side=None):
        """Returns {'codes': [...], 'plates': [...], 'texts': [...], 'ms': float}. Each code is a
        dict with code, valid (check digit OK), size_type, score, box (x, y, w, h) in frame pixels.
        Each plate: plate ('5188 VDA'), digits, letters, arabic, verified (Arabic row agrees),
        score, box, latin_box.
        zoom: if no check-digit-valid code is found, re-read around the likeliest serial
        number at 2x (small, far-away codes); costs one extra OCR pass only when needed.
        vertical: if still nothing valid, look for vertically stacked codes (container side
        corners) by detecting text on the frame rotated 90 degrees; one extra pass."""
        t0 = time.perf_counter()
        self.side = max_side or self.max_side  # this call's search size (per camera)
        out = self._read(frame)
        main_items = out['items']
        for c in out['codes']:
            if c['code'].endswith('?'):
                self._read_check_digit(frame, c, main_items)
        if zoom and not any(c['valid'] for c in out['codes']):
            # zoom on the unverified code if there is one, else the tallest number
            serials = [c['box'] for c in out['codes']] or sorted(
                (b for t, b in zip(out['texts'], out['boxes'])
                 if sum(ch.isdigit() for ch in t) >= 5 and not _is_overlay(t)),
                key=lambda b: -b[3])
            if serials:
                x, y, w, h = serials[0]
                x0, y0 = max(0, x - 4 * h), max(0, y - 2 * h)
                crop = frame[y0:y + 3 * h, x0:x + w + 4 * h]
                zoomed = self._read(cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
                found = [c for c in zoomed['codes'] if c['valid']]
                if found:
                    for c in found:
                        bx, by, bw, bh = c['box']
                        c['box'] = (x0 + bx // 2, y0 + by // 2, bw // 2, bh // 2)
                    serials = {c['code'][4:10] for c in found}
                    out['codes'] = found + [c for c in out['codes'] if c['code'][4:10] not in serials]
        self.calls += 1
        if vertical and self.calls % self.vertical_every == 0 and not any(c['valid'] for c in out['codes']):
            extra = self._vertical_items(frame)
            if extra:
                v = self._codes(out['items'] + extra)
                if any(c['valid'] for c in v['codes']) or not out['codes']:
                    out = v
        out['plates'] = [p for p in (self._plates(frame, main_items) if plates else [])
                         if not any(_overlaps(p['latin_box'], c['box']) for c in out['codes'])]
        out['ms'] = round((time.perf_counter() - t0) * 1000)
        del out['items']
        return out

    def _read_check_digit(self, frame, code, items):
        """The check digit is printed in a box right after the serial, and the box lines often
        hide it from the detector. Read just that spot; accept it only if it equals the digit
        computed from the other 10 characters (updates `code` in place)."""
        serial = code['code'][4:10]
        boxes = [b for t, _, b in items if _loose(t).endswith(_loose(serial))]
        if not boxes:
            return
        sx, sy, sw, sh = boxes[0]
        expected = str(check_digit(code['code'][:10]))
        y0, y1, x0 = max(0, sy - sh // 5), sy + sh + sh // 5, sx + sw
        # The box lines can swamp a single digit, so try the spot as is, without the box
        # border, and nudged right; any read only counts if it is the computed digit.
        for crop in (frame[y0:y1, x0:x0 + int(1.6 * sh)],
                     frame[sy + sh // 6:sy + sh - sh // 6, x0 + sh // 4:x0 + int(1.3 * sh)],
                     frame[y0:y1, x0 + sh // 3:x0 + 2 * sh]):
            text, _ = self._rec(self.engine, crop)
            if expected in {TO_DIGIT.get(ch, ch) for ch in normalize(text)}:
                code['code'], code['valid'] = code['code'][:10] + expected, True
                return

    def _rec(self, engine, crop):
        """Recognition only (no detection) on a crop scaled to the model's 48 px height."""
        if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
            return '', 0.0
        f = 48 / crop.shape[0]
        res, _ = engine(cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC),
                        use_det=False, use_cls=False)
        return (res[0][0], float(res[0][1])) if res else ('', 0.0)

    def _plates(self, frame, items, fallback=True):
        """Find Saudi plates: the Latin row in the main OCR pass, or (if none) white
        plate-shaped rectangles read row by row. Then cross-check with the Arabic row above."""
        found = []  # (digits, letters, score, latin_box)
        items = [it for it in items if not _is_overlay(it[0])]
        for t, s, b in items:
            if (p := parse_latin(t)):
                found.append((*p, s, b))
        for (ta, sa, ba), (tb, sb, bb) in ((a, b) for a in items for b in items if a is not b):
            # a digits box and a 3-letter box side by side on one line
            if ba[0] < bb[0] and abs(ba[1] - bb[1]) < 0.5 * ba[3] and _near(ba, bb) \
                    and 1 <= len(normalize(ta)) <= 4 and len(normalize(tb)) == 3 and (p := parse_latin(ta + tb)):
                found.append((*p, min(sa, sb), _union([ba, bb])))
        if not found and fallback:
            for x, y, w, h in _plate_candidates(frame):
                text, s = self._rec(self.engine, frame[y + h // 2:y + h, x:x + w])
                if (p := parse_latin(text)):
                    found.append((*p, s, (x, y + h // 2, w, h - h // 2)))
        plates = {}
        for digits, letters, score, (x, y, w, h) in found:
            key = digits + letters
            if key in plates and plates[key]['score'] >= score:
                continue
            # Arabic row sits directly above the Latin row, same width
            top_y = max(0, y - round(1.15 * h))
            top = frame[top_y:y, x:x + w]
            ar_texts = [self._rec(self.arabic, c)[0] for c in (top, top[:, :w // 2], top[:, w // 2:])]
            plates[key] = {
                'plate': format_plate(digits, letters), 'digits': digits, 'letters': letters,
                'arabic': to_arabic(digits, letters), 'verified': arabic_matches(ar_texts, digits, letters),
                'arabic_read': ar_texts[0], 'score': round(score, 3), 'latin_box': (x, y, w, h),
                'box': (x, top_y, w, y + h - top_y),
            }
        return sorted(plates.values(), key=lambda p: (p['verified'], p['score']), reverse=True)

    def _small(self, frame):
        scale = min(1.0, getattr(self, 'side', self.max_side) / max(frame.shape[:2]))
        small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) \
            if scale < 1 else frame
        return small, scale

    def _reread_column(self, frame, box, top_margin):
        """Unstack a vertical text column and recognize it as one line."""
        x, y, w, h = box
        m = max(2, w // 4)
        crop = frame[max(0, y - top_margin):y + h + m, max(0, x - m):x + w + m]
        line = unstack(crop) if crop.size else None
        if line is None:
            return None
        rec, _ = self.engine(line, use_det=False, use_cls=False)
        return (rec[0][0], float(rec[0][1]), box) if rec else None

    def _vertical_items(self, frame):
        """Stacked upright characters aren't found by the (horizontal) text detector, but on
        the frame rotated 90 degrees they form a normal-looking text line."""
        small, scale = self._small(frame)
        H = small.shape[0]
        boxes, _ = self.engine(cv2.rotate(small, cv2.ROTATE_90_CLOCKWISE), use_cls=False, use_rec=False)
        rects = sorted(cv2.boundingRect(np.array(p).astype(np.int32)) for p in boxes or [])
        # The boxed check digit is often detected as a separate piece: merge pieces on the
        # same line (in rotated space) that are close together
        merged = []
        for r in rects:
            if merged:
                mx, my, mw, mh = merged[-1]
                overlap = min(my + mh, r[1] + r[3]) - max(my, r[1])
                if overlap > 0.5 * min(mh, r[3]) and r[0] - (mx + mw) < 2 * max(mh, r[3]):
                    x0, y0 = min(mx, r[0]), min(my, r[1])
                    merged[-1] = (x0, y0, max(mx + mw, r[0] + r[2]) - x0, max(my + mh, r[1] + r[3]) - y0)
                    continue
            merged.append(r)
        items = []
        for xr, yr, wr, hr in merged:
            if wr < 4 * hr:  # not a long column
                continue
            # rotated (xr, yr) -> original (x = yr, y = H - 1 - xr)
            x, y, w, h = (int(v / scale) for v in (yr, H - xr - wr, hr, wr))
            item = self._reread_column(frame, (x, y, w, h), w // 4)
            if item:
                items.append(item)
        return items

    def _ocr(self, frame):
        """[(points in frame pixels, text, score)]: detect on the downscaled frame; read the
        boxes either from it (classic) or, with sharp, from the full-resolution frame."""
        small, scale = self._small(frame)
        if not self.sharp or scale == 1:
            result, _ = self.engine(small, use_cls=False)
            return [(np.array(p) / scale, t, s) for p, t, s in result or []]
        boxes, _ = self.engine(small, use_cls=False, use_rec=False)
        if not boxes:
            return []
        full = [np.array(b, dtype=np.float32) / scale for b in boxes]
        rec, _ = self.engine.text_rec(self.engine.get_crop_img_list(frame, full))
        return [(p, r[0], r[1]) for p, r in zip(full, rec) if r[1] >= self.engine.text_score]

    def _read(self, frame):
        items = []  # (text, score, (x, y, w, h)) in full-frame pixels
        for pts, text, score in self._ocr(frame):
            x, y, w, h = cv2.boundingRect(np.array(pts).astype(np.int32))
            items.append((text, float(score), (x, y, w, h)))
            if h > 2.5 * w:  # vertical side code: re-read it unstacked
                # the owner letters above are often missed by the detector
                item = self._reread_column(frame, (x, y, w, h), h // 2)
                if item:
                    items.append(item)
        return self._codes(items)

    def _codes(self, items):
        items = [it for it in items if not _is_overlay(it[0])]  # the camera's date/time stamp
        items += _columns(items)
        texts = [t for t, _, _ in items]
        size_type = find_size_type(texts)
        codes = []
        for code, valid in find_codes(texts, [b for _, _, b in items]).items():
            key = _loose(code.rstrip('?'))
            parts = [(s, b) for t, s, b in items if len(_loose(t)) >= 3 and _loose(t) in key]
            # The code must be backed by real text boxes covering most of it; otherwise it was
            # stitched from unrelated fragments that happen to pass the check digit.
            covered = sum(len(_loose(t)) for t, _, _ in items if len(_loose(t)) >= 3 and _loose(t) in key)
            if covered < 9:
                continue
            xs = [b[0] for _, b in parts] + [b[0] + b[2] for _, b in parts]
            ys = [b[1] for _, b in parts] + [b[1] + b[3] for _, b in parts]
            codes.append({
                'code': code, 'valid': valid, 'size_type': size_type,
                'score': round(sum(s for s, _ in parts) / len(parts), 3),
                'box': (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)),
            })
        codes.sort(key=lambda c: (c['valid'], c['score']), reverse=True)
        return {'codes': codes, 'texts': texts, 'boxes': [b for _, _, b in items], 'items': items}


def _is_overlay(text):
    """The camera's own date/time overlay ('10-15-2026 Thu 08:31:40'): never a container."""
    return ':' in text or text.count('-') >= 2 or sum(ch.isdigit() for ch in text) > 8


def _overlaps(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _union(boxes):
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return x0, y0, max(b[0] + b[2] for b in boxes) - x0, max(b[1] + b[3] for b in boxes) - y0


def _plate_candidates(frame):
    """White, plate-shaped rectangles (Saudi plates are white with dark print). The plate's
    divider lines are bridged by a closing so the whole plate is one blob."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 140), (180, 70, 255))
    k = max(3, frame.shape[0] // 300)
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    out = []
    for c in cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(c)
        if 1.1 <= w / h <= 3.6 and w * h >= 400 and h < 0.15 * frame.shape[0] \
                and cv2.contourArea(c) > 0.5 * w * h:
            out.append((x, y, w, h))
    return out


def draw(frame, codes, plates=()):
    """Draw boxes and labels in place: green = check digit OK, orange = unverified,
    blue = plate (darker when the Arabic row confirmed it)."""
    items = [(c['box'], (0, 200, 0) if c['valid'] else (0, 165, 255),
              format_code(c['code']) + (f"  {c['size_type']}" if c['size_type'] else '')) for c in codes]
    items += [(p['box'], (255, 120, 0) if p['verified'] else (255, 200, 80), p['plate']) for p in plates]
    for (x, y, w, h), color, label in items:
        thick = max(2, frame.shape[1] // 600)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, thick)
        font = max(0.6, frame.shape[1] / 1600)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font, thick)
        ty = y - 8 if y - th - 12 > 0 else y + h + th + 8
        cv2.rectangle(frame, (x, ty - th - 6), (x + tw + 6, ty + 6), color, -1)
        cv2.putText(frame, label, (x + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, font, (0, 0, 0), thick)
    return frame
