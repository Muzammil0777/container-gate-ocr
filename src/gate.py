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


class _CamGroup(_Group):
    """A _Group read by several cameras (items carry 'cam'): also keeps each camera's best photo."""

    def __init__(self, key):
        super().__init__(key)
        self.by_cam = {}  # camera -> (score, frame)

    def add(self, item, frame, now, window_s):
        super().add(item, frame, now, window_s)
        cam = item['cam']
        if cam not in self.by_cam or item['score'] > self.by_cam[cam][0]:
            self.by_cam[cam] = (item['score'], frame.copy())


class _Groups:
    def __init__(self, key, same, group=_Group):
        self.key, self.same, self.group, self.groups = key, same, group, []

    def add(self, item, frame, now, window_s):
        k = self.key(item)
        g = next((g for g in self.groups if self.same(k, g.key)), None)
        if g is None:
            g = self.group(k)
            g.first = now
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


class LaneTracker:
    """A gate lane: the cameras that see the same truck, e.g. two reading the container from
    different angles and one (ANPR) reading the plate. Their reads are combined into one event
    per truck visit, like GateTracker does for one camera:
    - container reads from all container cameras vote together (consensus, check digit);
      `cams_agree` counts the cameras that read the final number exactly at least once, so a
      container seen the same by both cameras is verified (`cams_agree == cams_expected`)
    - the plate comes from the plate cameras only, the container from the container cameras
    - a visit waits up to `pair_window_s` for the part it is missing (the plate camera sees the
      front, the container cameras the rear), and up to `max_wait_s` for the second container
      camera to agree; a second, different confirmed plate means the next truck has arrived
    - one event per truck: code, plate, frame (best container photo), frame2 (the other
      container camera's photo), plate_frame, cams_agree, cams_expected
    A lane of one camera that reads both behaves exactly like GateTracker. cameras: [(name,
    role)] with role 'container', 'plate' or 'both'. update() may be called from each camera's
    own thread."""

    def __init__(self, cameras, min_hits=2, window_s=15, cooldown_s=300, accept_unverified=True,
                 gap_s=5, max_wait_s=10, pair_window_s=30):
        self.roles = dict(cameras)
        self.reads_codes = any(r in ('container', 'both') for r in self.roles.values())
        self.reads_plates = any(r in ('plate', 'both') for r in self.roles.values())
        self.cams_expected = sum(r in ('container', 'both') for r in self.roles.values())
        self.pair_window_s = pair_window_s if len(self.roles) > 1 else 0  # one camera: GateTracker's rules
        self.min_hits, self.window_s, self.cooldown_s = min_hits, window_s, cooldown_s
        self.accept_unverified, self.gap_s, self.max_wait_s = accept_unverified, gap_s, max_wait_s
        self.logged = {}  # 'serial' or 'plate' key -> last event time
        self.visit = None
        self.lock = threading.Lock()

    def update(self, camera, codes, frame, now=None, plates=()):
        """Feed one camera's reads of one frame; returns a list of events. Call it for every
        processed frame, also empty ones, so visits can end."""
        now = time.time() if now is None else now
        role = self.roles.get(camera)
        with self.lock:
            codes = [{**c, 'cam': camera} for c in codes
                     if role in ('container', 'both') and not self._cooling(c['code'][4:10], now)]
            plates = [{**p, 'cam': camera} for p in plates
                      if role in ('plate', 'both') and not self._cooling(p['digits'] + p['letters'], now)]
            events = []
            v = self.visit
            if v and self._over(v, now):
                events += self._emit(now)
                v = None
            if codes or plates:
                if v is None:
                    v = self.visit = self._new_visit(now)
                v['last'] = now
                for c in codes:
                    v['codes'].add(c, frame, now, self.window_s)
                for p in plates:
                    v['plates'].add(p, frame, now, self.window_s)
                events += self._next_truck(now)
                v = self.visit
            if v:
                code, plate = self._confirmed(v)
                if code or plate:
                    v['first_ok'] = v['first_ok'] or now
                    complete = (code or not self.reads_codes) and (plate or not self.reads_plates)
                    agreed = self.cams_expected <= 1 or (code and self._agree(code) >= self.cams_expected)
                    waited = now - v['first_ok'] >= self.max_wait_s
                    if (complete and (agreed or waited)) or \
                            (waited and now - v['start'] >= self.pair_window_s):
                        events += self._emit(now)
            return events

    def flush(self, now=None):
        """Emit the visit in progress (end of a video file, or a camera stopped)."""
        with self.lock:
            return self._emit(time.time() if now is None else now)

    def _new_visit(self, now):
        return {'codes': _Groups(lambda c: c['code'], same_container, _CamGroup),
                'plates': _Groups(lambda p: p['digits'] + p['letters'], _same_plate, _CamGroup),
                'start': now, 'last': now, 'first_ok': None}

    def _over(self, v, now):
        """Nothing new for gap_s, and not waiting (within pair_window_s) for a missing part."""
        if now - v['last'] <= self.gap_s:
            return False
        code, plate = self._confirmed(v)
        missing = (self.reads_codes and not code) or (self.reads_plates and not plate)
        return not missing or now - v['start'] >= self.pair_window_s

    def _next_truck(self, now):
        """Two different confirmed plates in one visit: the first truck is done, the visit of
        the next one starts with its plate (its container comes after its plate)."""
        v, n = self.visit, self.min_hits
        ok = [g for g in v['plates'].groups if len(g.reads) >= n]
        if len(ok) < 2:
            return []
        nxt = max(ok, key=lambda g: g.first)
        v['plates'].groups.remove(nxt)
        events = self._emit(now)
        self.visit = self._new_visit(now)
        self.visit['plates'].groups.append(nxt)
        return events

    def _cooling(self, key, now):
        return now - self.logged.get(key, -1e18) < self.cooldown_s

    def _confirmed(self, v):
        n = self.min_hits
        code = v['codes'].confirmed(_resolve_code, lambda c: n if c['valid'] else 2 * n)
        if code and not code[0]['valid'] and not self.accept_unverified:
            code = None
        plate = v['plates'].confirmed(_resolve_plate, lambda p: n)
        return code, plate

    @staticmethod
    def _agree(code):
        """Container cameras that read the final number exactly, with a valid check digit."""
        item, group = code
        return len({it['cam'] for _, it in group.reads if it['code'] == item['code'] and it['valid']})

    def _emit(self, now):
        v = self.visit
        if not v:
            return []
        code, plate = self._confirmed(v)
        self.visit = None
        if not (code or plate):
            return []
        if code:
            self.logged[code[0]['code'][4:10]] = now
        if plate:
            self.logged[plate[0]['digits'] + plate[0]['letters']] = now
        frame = frame2 = None
        if code:
            best_cam = code[1].best[1]['cam']
            frame = code[1].best[2]
            others = sorted((s, f) for cam, (s, f) in code[1].by_cam.items() if cam != best_cam)
            frame2 = others[-1][1] if others else None
        return [{'code': code and code[0], 'plate': plate and plate[0],
                 'frame': frame if frame is not None else plate[1].best[2],
                 'frame2': frame2, 'plate_frame': plate and plate[1].best[2],
                 'cams_agree': self._agree(code) if code else None, 'cams_expected': self.cams_expected}]


class GateTracker(LaneTracker):
    """One camera reading both container and plate (a lane of one camera). A truck passing it
    is seen in many frames. Reads of its container code and of its plate are grouped (misreads
    of the same one vote together) and combined into one reading each (consensus across
    frames, the check digit settles look-alike digits). A reading is confirmed after
    `min_hits` reads within `window_s` (2x for a container whose check digit can't be
    confirmed). One event is emitted per truck visit:
    - as soon as both are confirmed, or
    - with whatever was confirmed after `max_wait_s`, or when nothing new has been read for
      `gap_s` (truck left, or one without container / with an unreadable plate).
    Logged codes and plates are then ignored for `cooldown_s` (truck waiting at the barrier).
    Call update() for every processed frame, also empty ones, so visits can end."""

    def __init__(self, min_hits=2, window_s=15, cooldown_s=300, accept_unverified=True,
                 gap_s=5, max_wait_s=10):
        super().__init__([('camera', 'both')], min_hits, window_s, cooldown_s, accept_unverified,
                         gap_s, max_wait_s)

    def update(self, codes, frame, now=None, plates=()):
        """Feed one frame's reads; returns a list of events (see LaneTracker)."""
        return super().update('camera', codes, frame, now, plates)


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
                if row.get(key) and row[key] != kept[key]:
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
