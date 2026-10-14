"""Container code recognition on a whole frame: RapidOCR (PP-OCRv4, ONNX) + ISO 6346 parsing."""
import time

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from src.iso6346 import TO_DIGIT, find_codes, find_size_type, format_code, normalize


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
    def __init__(self, max_side=1920, use_cuda=False):
        """max_side: frames are downscaled to this before OCR (speed vs. small far-away text).
        use_cuda needs `pip install onnxruntime-gpu` and an NVIDIA GPU."""
        self.max_side = max_side
        self.engine = RapidOCR(det_use_cuda=use_cuda, rec_use_cuda=use_cuda, cls_use_cuda=use_cuda)

    def __call__(self, frame, zoom=True, vertical=True):
        """Returns {'codes': [...], 'texts': [...], 'ms': float}. Each code is a dict with
        code, valid (check digit OK), size_type, score, box (x, y, w, h) in frame pixels.
        zoom: if no check-digit-valid code is found, re-read around the likeliest serial
        number at 2x (small, far-away codes); costs one extra OCR pass only when needed.
        vertical: if still nothing valid, look for vertically stacked codes (container side
        corners) by detecting text on the frame rotated 90 degrees; one extra pass."""
        t0 = time.perf_counter()
        out = self._read(frame)
        if zoom and not any(c['valid'] for c in out['codes']):
            serials = [b for t, b in zip(out['texts'], out['boxes'])
                       if sum(ch.isdigit() for ch in t) >= 5]
            if serials:
                x, y, w, h = max(serials, key=lambda b: b[3])
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
        if vertical and not any(c['valid'] for c in out['codes']):
            extra = self._vertical_items(frame)
            if extra:
                v = self._codes(out['items'] + extra)
                if any(c['valid'] for c in v['codes']) or not out['codes']:
                    out = v
        out['ms'] = round((time.perf_counter() - t0) * 1000)
        del out['items']
        return out

    def _small(self, frame):
        scale = min(1.0, self.max_side / max(frame.shape[:2]))
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

    def _read(self, frame):
        small, scale = self._small(frame)
        result, _ = self.engine(small, use_cls=False)
        items = []  # (text, score, (x, y, w, h)) in full-frame pixels
        for pts, text, score in result or []:
            x, y, w, h = cv2.boundingRect((np.array(pts) / scale).astype(np.int32))
            items.append((text, float(score), (x, y, w, h)))
            if h > 2.5 * w:  # vertical side code: re-read it unstacked
                # the owner letters above are often missed by the detector
                item = self._reread_column(frame, (x, y, w, h), h // 2)
                if item:
                    items.append(item)
        return self._codes(items)

    def _codes(self, items):

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


def draw(frame, codes):
    """Draw code boxes and labels in place: green = check digit OK, orange = unverified."""
    for c in codes:
        x, y, w, h = c['box']
        color = (0, 200, 0) if c['valid'] else (0, 165, 255)
        label = format_code(c['code']) + (f"  {c['size_type']}" if c['size_type'] else '')
        thick = max(2, frame.shape[1] // 600)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, thick)
        font = max(0.6, frame.shape[1] / 1600)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font, thick)
        ty = y - 8 if y - th - 12 > 0 else y + h + th + 8
        cv2.rectangle(frame, (x, ty - th - 6), (x + tw + 6, ty + 6), color, -1)
        cv2.putText(frame, label, (x + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, font, (0, 0, 0), thick)
    return frame
