"""Turn per-frame reads into one gate event per truck (plate + container) and log it:
snapshots on disk, one row in the database, Excel files per day and per month."""
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

from src.iso6346 import consensus_code, format_code, same_container
from src.recognizer import draw
from src.store import COLUMNS, LINKS, Store, to_excel  # noqa: F401  (COLUMNS/LINKS re-exported)


class _Group:
    """Reads that are probably of the same container (or plate) during one visit; misreads of
    it vote together instead of splitting the votes."""

    def __init__(self, key):
        self.key, self.reads, self.best = key, [], None  # reads: [(time, item)]; best: (score, item, frame)

    def add(self, item, frame, now, window_s):
        self.reads = [r for r in self.reads if now - r[0] <= window_s] + [(now, item)]
        if self.best is None or item['score'] > self.best[0]:
            self.best = (item['score'], item, frame.copy())


class _Groups:
    def __init__(self, key, same):
        self.key, self.same, self.groups = key, same, []

    def add(self, item, frame, now, window_s):
        k = self.key(item)
        g = next((g for g in self.groups if self.same(k, g.key)), None)
        if g is None:
            g = _Group(k)
            self.groups.append(g)
        g.add(item, frame, now, window_s)

    def confirmed(self, resolve, need):
        """(resolved item, group) for the most-read group that has enough reads, or None.
        resolve(group) -> item; need(item) -> required number of reads."""
        ok = []
        for g in self.groups:
            item = resolve(g)
            if len(g.reads) >= need(item):
                ok.append((len(g.reads), g.best[0], item, g))
        return max(ok, key=lambda x: x[:2])[2:] if ok else None


def _resolve_code(group):
    """The group's container code by consensus over all its reads (see consensus_code)."""
    code, valid = consensus_code([c['code'] for _, c in group.reads])
    return {**group.best[1], 'code': code, 'valid': valid}


def _resolve_plate(group):
    """The plate read most often (longest digits on a tie, '231 UTA' is a cut-off '3231 UTA')."""
    plates = [p for _, p in group.reads]
    names = [p['plate'] for p in plates]
    top = max(set(names), key=lambda n: (names.count(n), len(n)))
    pick = max((p for p in plates if p['plate'] == top), key=lambda p: (p['verified'], p['score']))
    return {**pick, 'verified': any(p['verified'] for p in plates if p['plate'] == top)}


def _same_plate(a, b):
    """'3231UTA' / '231UTA' / '3281UTA': same letters, digits equal, one a cut-off of the other,
    or one digit different."""
    da, la, db, lb = a[:-3], a[-3:], b[:-3], b[-3:]
    if la != lb:
        return False
    if len(da) == len(db):
        return sum(x != y for x, y in zip(da, db)) <= 1
    return da.endswith(db) or db.endswith(da)


class GateTracker:
    """A truck passing a camera is seen in many frames. Reads of its container code and of
    its plate are grouped (misreads of the same one vote together) and combined into one
    reading each (consensus across frames, the check digit settles look-alike digits). A
    reading is confirmed after `min_hits` reads within `window_s` (2x for a container whose
    check digit can't be confirmed). One event is emitted per truck visit:
    - as soon as both are confirmed, or
    - with whatever was confirmed after `max_wait_s`, or when nothing new has been read for
      `gap_s` (truck left, or one without container / with an unreadable plate).
    Logged codes and plates are then ignored for `cooldown_s` (truck waiting at the barrier).
    Call update() for every processed frame, also empty ones, so visits can end."""

    def __init__(self, min_hits=2, window_s=15, cooldown_s=300, accept_unverified=True,
                 gap_s=5, max_wait_s=10):
        self.min_hits, self.window_s, self.cooldown_s = min_hits, window_s, cooldown_s
        self.accept_unverified, self.gap_s, self.max_wait_s = accept_unverified, gap_s, max_wait_s
        self.logged = {}   # 'serial' or 'plate' key -> last event time
        self.visit = None

    def update(self, codes, frame, now=None, plates=()):
        """Feed one frame's reads; returns a list of events. An event is a dict with
        code (or None), plate (or None), frame, plate_frame."""
        now = time.time() if now is None else now
        codes = [c for c in codes if not self._cooling(c['code'][4:10], now)]
        plates = [p for p in plates if not self._cooling(p['digits'] + p['letters'], now)]
        events = []
        v = self.visit
        if v and now - v['last'] > self.gap_s:  # visit over
            events += self._emit(now)
            v = None
        if codes or plates:
            if v is None:
                v = self.visit = {'codes': _Groups(lambda c: c['code'], same_container),
                                  'plates': _Groups(lambda p: p['digits'] + p['letters'], _same_plate),
                                  'last': now, 'first_ok': None}
            v['last'] = now
            for c in codes:
                v['codes'].add(c, frame, now, self.window_s)
            for p in plates:
                v['plates'].add(p, frame, now, self.window_s)
        if v:
            code, plate = self._confirmed()
            if code or plate:
                v['first_ok'] = v['first_ok'] or now
                if (code and plate) or now - v['first_ok'] >= self.max_wait_s:
                    events += self._emit(now)
        return events

    def flush(self, now=None):
        """Emit the visit in progress (end of a video file)."""
        return self._emit(time.time() if now is None else now)

    def _cooling(self, key, now):
        return now - self.logged.get(key, -1e18) < self.cooldown_s

    def _confirmed(self):
        v, n = self.visit, self.min_hits
        code = v['codes'].confirmed(_resolve_code, lambda c: n if c['valid'] else 2 * n)
        if code and not code[0]['valid'] and not self.accept_unverified:
            code = None
        plate = v['plates'].confirmed(_resolve_plate, lambda p: n)
        return code, plate

    def _emit(self, now):
        if not self.visit:
            return []
        code, plate = self._confirmed()
        self.visit = None
        if not (code or plate):
            return []
        if code:
            self.logged[code[0]['code'][4:10]] = now
        if plate:
            self.logged[plate[0]['digits'] + plate[0]['letters']] = now
        return [{'code': code and code[0], 'plate': plate and plate[0],
                 'frame': (code or plate)[1].best[2], 'plate_frame': plate and plate[1].best[2]}]


class GateLog:
    """Logs gate events: saves the snapshots, stores one row per truck in the database
    (duplicates within dedupe_s merged, see Store.add), and keeps an Excel file per day and
    per month in excel_dir up to date. Excel files are rewritten by flush() (called every few
    seconds by the camera loop); a file open in Excel is simply retried later, the data is
    safe in the database either way. Thread-safe."""

    def __init__(self, store=None, snapshot_dir='logs/snapshots', excel_dir='logs/excel', language='en',
                 dedupe_s=300):
        self.store = store or Store()
        self.snapshot_dir, self.excel_dir = Path(snapshot_dir), Path(excel_dir)
        self.lang, self.dedupe_s = language, dedupe_s
        self.dirty, self.lock = set(), threading.Lock()  # days ('YYYY-MM-DD') whose Excel is stale

    def log(self, event, camera='camera', location='', direction='', when=None):
        """Save the snapshots and store one row. Returns the row dict, with 'status'
        ('added', 'merged' or 'duplicate') and 'id'."""
        when = when or datetime.now()
        code, plate = event['code'], event['plate']
        day_dir = self.snapshot_dir / when.strftime('%Y-%m-%d')
        day_dir.mkdir(parents=True, exist_ok=True)
        name = '_'.join(x for x in (code and code['code'].rstrip('?'),
                                    plate and plate['digits'] + plate['letters']) if x)
        stem = f"{when:%H%M%S}_{_safe(camera)}_{name}"
        snap = day_dir / f"{stem}.jpg"
        cv2.imwrite(str(snap), draw(event['frame'].copy(), [code] if code else [], [plate] if plate else []))
        plate_img = ''
        if plate:
            x, y, w, h = plate['box']
            m = max(4, h // 4)
            crop = event['plate_frame'][max(0, y - m):y + h + m, max(0, x - m):x + w + m]
            if crop.size:
                f = max(1.0, 120 / crop.shape[0])
                cv2.imwrite(str(day_dir / f"{stem}_plate.jpg"),
                            cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC))
                plate_img = str((day_dir / f"{stem}_plate.jpg").resolve())
        row = {
            'date': when.strftime('%Y-%m-%d'), 'time': when.strftime('%H:%M:%S'), 'direction': direction or None,
            'plate': plate['plate'] if plate else None, 'plate_ar': plate['arabic'] if plate else None,
            'plate_verified': int(plate['verified']) if plate else None,
            'container': format_code(code['code']) if code else None,
            'check_digit_ok': int(code['valid']) if code else None,
            'size_type': (code['size_type'] or None) if code else None,
            'camera': camera, 'location': location,
            'confidence': round(min(x['score'] for x in (code, plate) if x), 3),
            'snapshot': str(snap.resolve()), 'plate_image': plate_img or None,
        }
        row['status'], row['id'] = self.store.add(row, self.dedupe_s)
        if row['status'] != 'added':  # the earlier row keeps its photos; drop the unused new ones
            kept = self.store.get(row['id'])
            for key in LINKS:
                if row[key] and row[key] != kept[key]:
                    Path(row[key]).unlink(missing_ok=True)
        if row['status'] != 'duplicate':
            self.changed(row['date'])
        return row

    def changed(self, day):
        """Mark a day's (and its month's) Excel files for rewriting, e.g. after a correction."""
        with self.lock:
            self.dirty.add(day)

    def flush(self):
        """Rewrite the Excel files of changed days and their months. Returns the days that
        are still pending because a file is open in another program."""
        with self.lock:
            days, self.dirty = self.dirty, set()
        pending = set()
        for day in sorted(days):
            for name, rows in ((f'gate_log_{day}', self.store.day(day)),
                               (f'gate_log_{day[:7]}', self.store.month(day[:7]))):
                try:
                    self.excel_dir.mkdir(parents=True, exist_ok=True)
                    tmp = self.excel_dir / f'{name}.tmp'
                    tmp.write_bytes(to_excel(rows, self.lang))
                    tmp.replace(self.excel_dir / f'{name}.xlsx')
                except PermissionError:
                    pending.add(day)
        if pending:
            print(f"[gate] Excel file for {', '.join(sorted(pending))} is open in another program; "
                  f"it will be updated when it's closed (the data is safe in the database).")
            with self.lock:
                self.dirty |= pending
        return pending


def _safe(name):
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
