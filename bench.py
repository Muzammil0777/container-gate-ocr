"""Benchmark the gate pipeline on recorded CCTV footage, as if it were the live camera.

    py -3.12 bench.py "C:/path/to/nvr_export.mp4" --fps 2 --out bench_out
    py -3.12 bench.py lane_rear_left.mp4 lane_rear_right.mp4 anpr.mp4   # cameras sharing one PC
    py -3.12 bench.py one_camera.mp4 --copies 3                         # the same, from one recording

Reads the video at --fps frames per video-second (like the live camera loop), runs the
recognizer + gate tracker on each, and reports per-frame speed and every truck that would
have been logged. Writes <out>/reads.jsonl (all reads per frame) and <out>/trucks.csv.
--realtime additionally reports how many frames a live camera would have skipped because
OCR was slower than the video.

With several videos (or --copies), they play at the same time in real time, sharing one OCR
engine like the live service's cameras do, and each reports its looks per second.
"""
import argparse
import csv
import json
import threading
import time
from pathlib import Path

import cv2

from src.gate import GateTracker
from src.iso6346 import format_code
from src.recognizer import Recognizer
from src.scanner import Scanner


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video', nargs='+', help='one recording, or several to play at the same time')
    ap.add_argument('--copies', type=int, default=1, help='play the recording(s) this many times at once')
    ap.add_argument('--fps', type=float, default=2, help='frames analysed per second of video')
    ap.add_argument('--start', type=float, default=0, help='start at this video second')
    ap.add_argument('--end', type=float, default=None, help='stop at this video second')
    ap.add_argument('--max-side', type=int, default=1920)
    ap.add_argument('--classic', action='store_true', help='read text from the downscaled frame (old method)')
    ap.add_argument('--follow', action='store_true', help='full scans + quick re-reads of where text was found')
    ap.add_argument('--roi', help='only read this part of the frame: x0,y0,x1,y1 as fractions, e.g. 0,0,0.66,0.78')
    ap.add_argument('--realtime', action='store_true',
                    help='skip frames while OCR is busy, exactly like a live camera (honest live numbers)')
    ap.add_argument('--out', default='bench_out')
    args = ap.parse_args()
    videos = args.video * args.copies
    if len(videos) > 1:
        return streams(videos, args)
    args.video = videos[0]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, round(vfps / args.fps))
    recognizer = Recognizer(max_side=args.max_side, sharp=not args.classic, vertical_every=3)
    tracker = GateTracker()
    scanner = Scanner(recognizer) if args.follow else None
    roi = [float(v) for v in args.roi.split(',')] if args.roi else None
    recognizer(cap.read()[1])  # warm up the models, not part of the timing
    reads, trucks, times = open(out / 'reads.jsonl', 'w', encoding='utf-8'), [], []
    n, t_start, next_s = 0, time.time(), 0.0

    def record(events, now):
        for e in events:
            c, p = e['code'], e['plate']
            trucks.append({'video_s': round(now, 1), 'plate': p['plate'] if p else '',
                           'plate_verified': p['verified'] if p else '',
                           'container': format_code(c['code']) if c else '',
                           'check_digit_ok': c['valid'] if c else ''})
            print(f"  {now:6.1f} s  TRUCK  plate {trucks[-1]['plate'] or '-':<9} "
                  f"container {trucks[-1]['container'] or '-'}")

    while True:
        ok = cap.grab()
        if not ok:
            break
        now = n / vfps
        n += 1
        if now < max(args.start, next_s) or (not args.realtime and (n - 1) % step):
            continue
        if args.end is not None and now > args.end:
            break
        _, frame = cap.retrieve()
        if roi:
            H, W = frame.shape[:2]
            frame = frame[int(roi[1] * H):int(roi[3] * H), int(roi[0] * W):int(roi[2] * W)]
        o = scanner(frame, now, zoom=False) if scanner else recognizer(frame)  # --follow = live settings
        times.append(o['ms'])
        if args.realtime:  # a live camera only gets its next frame once OCR is done (and at most --fps)
            next_s = now + max(1 / args.fps, o['ms'] / 1000)
        reads.write(json.dumps({'video_s': round(now, 2), 'ms': o['ms'], 'mode': o.get('mode', 'full'),
                                'codes': [(c['code'], c['valid']) for c in o['codes']],
                                'plates': [(p['plate'], p['verified']) for p in o['plates']],
                                'texts': o['texts']}, ensure_ascii=False) + '\n')
        if o['codes'] or o['plates']:
            print(f"  {now:6.1f} s  {o['ms']:5} ms {o.get('mode', ''):6} codes {[c['code'] for c in o['codes']]}  "
                  f"plates {[p['plate'] for p in o['plates']]}")
        record(tracker.update(o['codes'], frame, now, o['plates']), now)
    record(tracker.flush(n / vfps), n / vfps)
    reads.close()
    with open(out / 'trucks.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, ['video_s', 'plate', 'plate_verified', 'container', 'check_digit_ok'])
        w.writeheader()
        w.writerows(trucks)
    times.sort()
    if times:
        avg = sum(times) / len(times)
        print(f"\n{len(times)} frames analysed in {time.time() - t_start:.0f} s | per frame: avg {avg:.0f} ms, "
              f"median {times[len(times) // 2]} ms, slowest {times[-1]} ms | live capacity ~{1000 / avg:.2f} frames/s")
    print(f"{len(trucks)} truck(s) logged -> {out / 'trucks.csv'}")


def streams(videos, args):
    """Play several recordings at once in real time, like live cameras on one computer: every
    stream decodes all its frames, and they take turns on one OCR engine (as cctv.py does)."""
    roi = [float(v) for v in args.roi.split(',')] if args.roi else None
    recognizer = Recognizer(max_side=args.max_side, vertical_every=3)
    recognizer(cv2.VideoCapture(videos[0]).read()[1])  # warm up the models, not part of the timing
    lock, results, t0 = threading.Lock(), [None] * len(videos), time.time()

    def play(i, video):
        cap = cv2.VideoCapture(video)
        vfps = cap.get(cv2.CAP_PROP_FPS) or 25
        scanner, tracker = Scanner(recognizer), GateTracker()
        looks, ms, waited, trucks, n, last = 0, 0, 0.0, 0, 0, -1e9
        while True:
            now = time.time() - t0  # this stream's position = wall time since the start (live)
            while n / vfps < now:   # decode every frame up to now, like a live stream
                if not cap.grab():
                    results[i] = (video, looks, ms, waited, trucks, n / vfps)
                    return
                n += 1
            if args.end is not None and now > args.end:
                break
            if now - last < 1 / args.fps:
                time.sleep(0.005)
                continue
            last = now
            _, frame = cap.retrieve()
            if roi:
                H, W = frame.shape[:2]
                frame = frame[int(roi[1] * H):int(roi[3] * H), int(roi[0] * W):int(roi[2] * W)]
            t_wait = time.time()
            with lock:
                waited += time.time() - t_wait
                o = scanner(frame, now, zoom=False, max_side=1600 if roi else args.max_side)
            looks, ms = looks + 1, ms + o['ms']
            trucks += len(tracker.update(o['codes'], frame, now, o['plates']))
        results[i] = (video, looks, ms, waited, trucks + len(tracker.flush(now)), now)

    threads = [threading.Thread(target=play, args=(i, v)) for i, v in enumerate(videos)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    print(f"\n{len(videos)} streams at once, up to {args.fps} looks/s each:")
    for i, (video, looks, ms, waited, trucks, secs) in enumerate(results):
        print(f"  {i + 1}. {Path(video).name:<28} {looks / secs:5.2f} looks/s | OCR avg {ms / max(looks, 1):5.0f} ms | "
              f"waiting for other cameras {100 * waited / secs:3.0f}% | {trucks} truck(s)")
    total = sum(r[1] / r[5] for r in results)
    print(f"  all streams together: {total:.2f} looks/s")


if __name__ == '__main__':
    main()
