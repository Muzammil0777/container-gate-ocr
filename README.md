# Container Code Recognition

Reads shipping-container codes (ISO 6346, e.g. `TRLU 668957 4  45G1`) from images, videos
and live CCTV cameras, and logs every truck entering or leaving a gate to Excel with date,
time, direction, camera, location and a snapshot.

Everything is free and runs on a normal CPU: no GPU, no cloud, no paid API.

![Output example](./output.jpg?raw=true "Output example")

## How it works

1. **OCR on the whole frame**: [RapidOCR](https://github.com/RapidAI/RapidOCR) (PaddleOCR
   PP-OCRv4 models running on ONNX Runtime) finds and reads all text. No custom detector
   or training needed.
2. **ISO 6346 parsing** ([src/iso6346.py](src/iso6346.py)): finds `owner(3) + U/J/Z +
   serial(6) + check digit` in the text, even when the pieces are separate boxes in any
   order. OCR confusions (`0↔O/U`, `8↔B`, `1↔I`, `6↔G`…) are fixed **only when the check
   digit confirms the fix**. Pieces far apart in the image are never combined.
3. **Recovery passes** ([src/recognizer.py](src/recognizer.py)), only when no valid code
   was found: the area around the serial number is re-read at 2× zoom (recovers small or
   far-away check digits), and vertical side codes, which the text detector can't see,
   are found on the frame rotated 90°, split into characters and re-read as one line.
4. **Gate logic** ([src/gate.py](src/gate.py)): a truck is seen in many frames, so a code
   must be read several times before it's logged once, then it's ignored for a cooldown
   while the truck waits at the barrier.

**Accuracy on `images/`:** 14 of 19 images give a check-digit-confirmed code, 1 gives an
unverified one, 0 false codes. The misses are blurry or partial vertical crops. About 0.5–1 s
per 1080p frame on CPU. Run `python -m pytest` to check (see `tests/test_samples.py`).

## Setup

```bash
pip install -r requirements.txt
```

Python 3.9+. The OCR models (~15 MB) ship inside the `rapidocr_onnxruntime` package.

## 1. Try it: Streamlit demo

```bash
streamlit run app.py
```

| Tab | What it does |
|---|---|
| 📷 Image | Upload photos (or pick a sample) and see the codes, check digit status and timing |
| 🎞️ Video → gate log | Upload a gate video: simulates the CCTV logger and lets you download the Excel log |
| 📡 Camera test | Paste an RTSP URL and grab one frame to check the camera angle is readable |
| 📒 Gate log | Browse the Excel logs and snapshots written by `cctv.py` |

Single image from the command line: `python single_frame_process.py -i images/container1.png`

## 2. Run it on CCTV cameras

```bash
copy cameras.example.json cameras.json      # then edit it
python cctv.py --config cameras.json
```

One camera per lane: set `"direction": "IN"` on the entry camera and `"OUT"` on the exit
camera. `cameras.json` holds camera passwords, so it's git-ignored. Common RTSP URLs:

| Brand | URL |
|---|---|
| Hikvision | `rtsp://USER:PASS@IP:554/Streaming/Channels/101` |
| Dahua / Amcrest | `rtsp://USER:PASS@IP:554/cam/realmonitor?channel=1&subtype=0` |
| Webcam / test | `0`, or a video file path |

Quick single-camera test: `python cctv.py --source videos/gate.mp4 --direction IN --location "Gate 1" --show`

**Excel log:** `logs/gate_log_YYYY-MM.xlsx` (one workbook per month)

| Date | Time | Container Code | Check Digit OK | Size/Type | Direction | Camera | Location | Confidence | Snapshot |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-14 | 14:13:57 | TCNU 634580 7 | YES | 45G1 | IN | Gate 1 Entry | Main gate | 0.89 | open image |

Snapshots with the code highlighted are saved to `logs/snapshots/YYYY-MM-DD/`, linked from
the Snapshot column.

**Behaviour you should know about**
- Rows with `Check Digit OK = NO` mean the check digit was unreadable (shown as `?`) or
  didn't match. They're logged rather than dropped, so a truck is never silently missed.
  Check them against the snapshot, or set `"accept_unverified": false`.
- **Don't keep the live workbook open in Excel.** Windows locks it. Rows are then queued in
  memory and written once it's closed (a warning is printed), but nothing reaches the file
  while it's open. Use the Streamlit *Gate log* tab, or open a copy.
- Live streams always process the newest frame, so OCR never lags behind the feed. Dropped
  RTSP connections reconnect automatically, and a static empty scene is only re-checked
  every 2 s to save CPU.

**Run on startup (free):** Windows Task Scheduler → *Create Task* → trigger *At startup* →
action `python cctv.py --config cameras.json` with *Start in* set to this folder.

**Settings** (`cameras.json`, all optional)

| Key | Default | Meaning |
|---|---|---|
| `fps` | 2 | OCR passes per second per camera |
| `min_hits` | 2 | Valid reads needed before logging (unverified codes need 2×) |
| `cooldown_s` | 300 | Ignore the same container on the same camera for this long |
| `max_side` | 1920 | Frames are downscaled to this before OCR |
| `use_cuda` | false | NVIDIA GPU: `pip install onnxruntime-gpu`, then set `true` |

## Known limitations / next steps

- Vertical (stacked) side codes are found by a rotated detection pass (e.g. `images/side_vertical_ffau.jpg`), but blurry or very narrow crops are still missed (`code4`, `face2`).
  The best free fix is a better camera angle: face the rear doors and get at least 20 px
  of character height.
- Direction comes from the camera, not from vehicle movement. A single camera covering
  both directions would need motion tracking.
- If accuracy needs to go further, fine-tune the PP-OCR recognition model on your own gate
  footage. It's free on Google Colab or Kaggle GPUs.

## Development

```bash
python -m pytest        # unit tests + accuracy regression on images/
```

Troubleshooting (Windows): `DLL load failed while importing onnxruntime_pybind11_state`
happens when `pandas`/`pyarrow` is imported before `onnxruntime`. Import `src.recognizer`
first (as `app.py` does), or `pip install -U onnxruntime pyarrow`.
