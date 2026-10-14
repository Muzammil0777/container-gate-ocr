"""Turn per-frame reads into gate events and log them to Excel with a snapshot."""
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from src.iso6346 import format_code
from src.recognizer import draw

COLUMNS = ['Date', 'Time', 'Container Code', 'Check Digit OK', 'Size/Type', 'Direction',
           'Camera', 'Location', 'Confidence', 'Snapshot']


class GateTracker:
    """A truck passing a camera is seen in many frames. Emit one event per code once it was
    read `min_hits` times within `window_s`, then ignore it for `cooldown_s` (truck waiting
    at the barrier). Codes without a confirmed check digit (the boxed digit is often
    unreadable on CCTV) need 2x the hits; they are logged flagged rather than dropped,
    since a missing truck is worse than a row to double-check against its snapshot."""

    def __init__(self, min_hits=2, window_s=15, cooldown_s=300, accept_unverified=True):
        self.min_hits, self.window_s, self.cooldown_s = min_hits, window_s, cooldown_s
        self.accept_unverified = accept_unverified
        self.hits = defaultdict(list)   # code -> [timestamps]
        self.best = {}                  # code -> (score, code dict, frame)
        self.logged = {}                # serial -> last event time

    def update(self, codes, frame, now=None):
        """Feed one frame's codes; returns a list of (code dict, best frame) to log."""
        now = time.time() if now is None else now
        events = []
        for c in codes:
            if not c['valid'] and not self.accept_unverified:
                continue
            code, serial = c['code'], c['code'][4:10]
            if now - self.logged.get(serial, -1e18) < self.cooldown_s:
                continue
            self.hits[code] = [t for t in self.hits[code] if now - t <= self.window_s] + [now]
            if code not in self.best or c['score'] > self.best[code][0]:
                self.best[code] = (c['score'], c, frame.copy())
            if len(self.hits[code]) >= self.min_hits * (1 if c['valid'] else 2):
                _, best_c, best_frame = self.best.pop(code)
                events.append((best_c, best_frame))
                self.logged[serial] = now
                # forget other spellings of this container
                for k in [k for k in self.hits if k[4:10] == serial]:
                    self.hits.pop(k)
                    self.best.pop(k, None)
        return events


class ExcelLog:
    """Append-only Excel log. `path` may contain strftime codes, e.g. logs/gate_%Y-%m.xlsx
    for one workbook per month. Thread-safe. If the workbook is open in Excel (locked on
    Windows), rows are queued and written on the next append/flush instead of being lost."""

    def __init__(self, path='logs/gate_log_%Y-%m.xlsx', snapshot_dir='logs/snapshots'):
        self.path, self.snapshot_dir = path, Path(snapshot_dir)
        self.pending = []
        self.lock = threading.Lock()

    def log(self, code, frame, camera='camera', location='', direction='', when=None):
        """Save the snapshot and append one row. Returns the row as a dict."""
        when = when or datetime.now()
        day_dir = self.snapshot_dir / when.strftime('%Y-%m-%d')
        day_dir.mkdir(parents=True, exist_ok=True)
        snap = day_dir / f"{when:%H%M%S}_{_safe(camera)}_{code['code'].rstrip('?')}.jpg"
        cv2.imwrite(str(snap), draw(frame.copy(), [code]))
        row = {
            'Date': when.strftime('%Y-%m-%d'), 'Time': when.strftime('%H:%M:%S'),
            'Container Code': format_code(code['code']), 'Check Digit OK': 'YES' if code['valid'] else 'NO',
            'Size/Type': code['size_type'] or '', 'Direction': direction, 'Camera': camera,
            'Location': location, 'Confidence': code['score'], 'Snapshot': str(snap.resolve()),
        }
        with self.lock:
            self.pending.append((when, row))
            self._flush()
        return row

    def flush(self):
        with self.lock:
            self._flush()

    def _flush(self):
        while self.pending:
            when, row = self.pending[0]
            path = Path(when.strftime(self.path))
            try:
                if path.exists():
                    wb = load_workbook(path)
                    ws = wb.active
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    wb = Workbook()
                    ws = wb.active
                    ws.title = 'Gate log'
                    ws.append(COLUMNS)
                    for cell in ws[1]:
                        cell.font = Font(bold=True)
                    ws.freeze_panes = 'A2'
                ws.append([row[c] for c in COLUMNS])
                link = ws.cell(row=ws.max_row, column=len(COLUMNS))
                link.hyperlink, link.value, link.style = row['Snapshot'], 'open image', 'Hyperlink'
                wb.save(path)
            except PermissionError:
                print(f"[gate] {path} is open in another program, {len(self.pending)} row(s) "
                      f"queued; close it and they will be written on the next event.")
                return
            self.pending.pop(0)


def _safe(name):
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
