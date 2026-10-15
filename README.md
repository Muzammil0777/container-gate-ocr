# Container Gate OCR

Reads **shipping-container codes** (ISO 6346, e.g. `MRSU 442576 1  45G1`) and **Saudi number
plates** (e.g. `3231 UTA` / `و ط ا ٣٢٣١`) from images, videos and live CCTV cameras, and logs
every truck entering or leaving a gate to Excel: date, time, direction, plate (Latin and
Arabic), container code, camera, location, a snapshot and a plate close-up.
English and Arabic app and Excel.

Everything is free and runs on a normal CPU: no GPU, no cloud, no paid API.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://container-gate-ocr.streamlit.app/)
**Live demo: https://container-gate-ocr.streamlit.app/**. Upload a photo of a truck with a
container and see the code and plate it reads.

![Output example](./output.jpg?raw=true "Output example")

## How it works

1. **OCR on the whole frame**: [RapidOCR](https://github.com/RapidAI/RapidOCR) (PaddleOCR
   models on ONNX Runtime) finds and reads all text. No custom detector or training needed.
2. **Container codes** ([src/iso6346.py](src/iso6346.py)): finds `owner(3) + U/J/Z +
   serial(6) + check digit`, even when the pieces are separate boxes in any order. OCR
   confusions (`0↔O/U`, `8↔B`, `1↔I`…) are fixed **only when the check digit confirms
   the fix**. Pieces far apart in the image are never combined.
3. **Recovery passes** ([src/recognizer.py](src/recognizer.py)), only when needed:
   - the boxed check digit is read on its own, and accepted only if it equals the computed digit
   - the code area is re-read at 2× zoom
   - vertical side codes are found on the frame rotated 90° and re-read as one line
4. **Saudi plates** ([src/saudi_plate.py](src/saudi_plate.py)): a Saudi plate prints the
   number twice, in Latin on the bottom row and in Arabic on the top row. Only 17 letters
   are used, each with one fixed Arabic/Latin pair (A=ا, B=ب, J=ح, D=د, R=ر, S=س, X=ص, T=ط,
   E=ع, G=ق, K=ك, L=ل, Z=م, N=ن, H=هـ, U=و, V=ى).
   - The Latin row is read first. If it isn't found in the main pass, white plate-shaped
     rectangles are tried.
   - The Arabic row is then read with an Arabic recognition model (PP-OCRv5).
   - When both rows agree, the plate is marked **verified**, much like a container check digit.
5. **Gate logic** ([src/gate.py](src/gate.py)): a truck is seen in many frames. The plate
   and the container are each confirmed after several reads, then logged together as
   **one Excel row per truck**. The same truck is then ignored for a cooldown while it
   waits at the barrier.

**Accuracy on `images/`** (`python -m pytest`, see `tests/test_samples.py`):

| | Result |
|---|---|
| Container codes | 18 of 22 images give a check-digit-confirmed code, 0 false codes (misses are blurry vertical crops) |
| Saudi plates | 3 of 3 read, all confirmed by the Arabic row; no confirmed plate on any non-Saudi image |
| Speed | About 1–2.5 s per frame on a laptop CPU |

## Setup

```bash
pip install -r requirements.txt
```

Python 3.9+. The main OCR models ship inside `rapidocr_onnxruntime`. The Arabic plate model
is in `models/` (8 MB, Apache-2.0, from [RapidAI/RapidOCR](https://www.modelscope.cn/models/RapidAI/RapidOCR)).

## 1. Try it: Streamlit demo

Use the hosted demo at https://container-gate-ocr.streamlit.app/, or run it locally
(faster, and it can reach cameras on your own network):

```bash
streamlit run app.py
```

Switch between **English / العربية** at the top of the sidebar. In Arabic the whole app
switches to a right-to-left layout.

| Tab | What it does |
|---|---|
| 📷 Image | Upload photos (or pick a sample) and see the container code, plate, check status and timing |
| 🎞️ Video → gate log | Upload a gate video: simulates the CCTV logger and lets you download the Excel log |
| 📡 Camera test | Paste an RTSP URL and grab one frame to check the camera angle is readable |
| 📒 Gate log | Browse the Excel logs (English or Arabic) and snapshots written by `cctv.py` |

Single image from the command line: `python single_frame_process.py -i images/ksa_mrsu_3231uta.jpg`

## 2. Run it on CCTV cameras

### On site with a Hikvision NVR

1. Connect the laptop to the NVR's network (same switch or Wi-Fi). Get the NVR's IP
   address and a username/password from the site; the IP is also on the NVR's monitor
   under *Menu → Configuration → Network*.
2. **Find the cameras:** double-click `find_cameras.bat`, or run `py -3.12 cctv.py --scan`.
   It asks for the IP, username and password (hidden), checks the connection, and saves a
   snapshot of every working channel to `logs\scan\`. Note the channel that sees the back
   of the trucks.
3. **Start the app:** double-click `start_gate.bat` (or `py -3.12 -m streamlit run app.py
   --server.port 8502`) and open the **🔴 Live** tab at http://localhost:8502.
4. **Start a camera:** in *➕ Start a camera*, enter the NVR IP, username, password and the
   channel, plus a camera name, direction (IN/OUT) and location, then press
   **▶ Start live detection**. Repeat this for each gate camera.
   - The Live tab shows each camera with its detections, refreshed every 2 s, plus the
     latest trucks logged.
   - Every truck becomes one Excel row (plate and container) as it passes.
   - Detection keeps running with the browser closed, as long as the app's PowerShell
     window stays open.
   - With *Remember and start automatically* ticked, the settings are saved to
     `cameras.json` on this computer, and the cameras start again whenever the app is opened.

If the scan or the Start button can't connect, it tells you whether the problem is the
network (wrong IP, laptop on another network) or the login (wrong password, account
locked, RTSP disabled). Streams use RTSP over TCP with automatic reconnect.

**Duplicates:** the Excel log is checked before every write. The same container or plate in
the same direction within `cooldown_s` (5 minutes) is never added twice, even across
restarts or two cameras. If the repeat reading adds something the first row was missing (a
plate, or a confirmed check digit), the earlier row is filled in instead.

### Running without the app (headless)

`cctv.py` does the same logging without the app, e.g. as a Windows startup task. Don't run
both for the same camera: duplicates are still prevented, but the CPU does the work twice.

```bash
copy cameras.example.json cameras.json      # then edit it
python cctv.py --config cameras.json
```

Point each camera at the back of the trailer, so it sees both the container doors and the
rear number plate. Use one camera per lane: set `"direction": "IN"` on the entry camera and
`"OUT"` on the exit camera. `cameras.json` holds camera passwords, so it's git-ignored.
Common RTSP URLs:

| Brand | URL |
|---|---|
| Hikvision | `"nvr"` block + `"channel"` (or `rtsp://USER:PASS@IP:554/Streaming/Channels/101`) |
| Dahua / Amcrest | `rtsp://USER:PASS@IP:554/cam/realmonitor?channel=1&subtype=0` |
| Webcam / test | `0`, or a video file path |

Quick single-camera test: `python cctv.py --source videos/gate.mp4 --direction IN --location "Gate 1" --show`

**Excel log:** `logs/gate_log_YYYY-MM.xlsx`, one workbook per month and one row per truck.
With `"language": "ar"`, the headers and values are in Arabic and the sheet is right-to-left.

| Date | Time | Direction | Plate | Plate (Arabic) | Plate Check | Container Code | Check Digit OK | Size/Type | Camera | Location | Confidence | Snapshot | Plate Image |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-14 | 16:06:14 | IN | 3231 UTA | و ط ا ٣٢٣١ | Arabic + Latin match | MRSU 442576 1 | YES | 45G1 | Gate 1 Entry | Dammam gate | 0.986 | open image | open image |

Snapshots (code and plate highlighted) and plate close-ups are saved to
`logs/snapshots/YYYY-MM-DD/` and linked from the last two columns.

**Behaviour you should know about**
- **When a row is written:** as soon as both the plate and the container are confirmed.
  If one of them can't be read (or the truck has no container), the row is written after
  10 s, or 5 s after the truck leaves the view, with that field left empty.
- **`Plate Check = Latin only`:** the Arabic row couldn't confirm the Latin reading. The
  Arabic plate is still filled in, converted from the Latin letters. Check against the
  plate close-up.
- **`Check Digit OK = NO`:** the container's check digit was unreadable (shown as `?`) or
  didn't match. Such rows are logged rather than dropped, so a truck is never silently
  missed. Set `"accept_unverified": false` to drop them.
- **Don't keep the live workbook open in Excel.** Windows locks it. Rows are then queued in
  memory and written once it's closed (a warning is printed), but nothing reaches the file
  while it's open. Use the Streamlit *Gate log* tab, or open a copy.
- **Workbooks with older columns or another language are never mixed.** New rows go to
  `..._2.xlsx` instead.
- **Live streams:** the newest frame is always processed, so OCR never lags behind the
  feed. Dropped RTSP connections reconnect automatically, and a static empty scene is only
  re-checked every 2 s to save CPU.

**Run on startup (free):** Windows Task Scheduler → *Create Task* → trigger *At startup* →
action `python cctv.py --config cameras.json` with *Start in* set to this folder.

**Settings** (`cameras.json`, all optional)

| Key | Default | Meaning |
|---|---|---|
| `language` | `en` | Excel headers and values: `en` or `ar` |
| `plates` | true | Read Saudi number plates |
| `fps` | 2 | OCR passes per second per camera |
| `min_hits` | 2 | Reads needed to confirm a code/plate (2× without check digit / Arabic match) |
| `gap_s` / `max_wait_s` | 5 / 10 | When a truck's row is written if only one of plate/container was read |
| `cooldown_s` | 300 | Ignore the same container or plate for this long |
| `max_side` | 1920 | Frames are downscaled to this before OCR |
| `use_cuda` | false | NVIDIA GPU: `pip install onnxruntime-gpu`, then set `true` |

## Known limitations / next steps

- **Saudi plates only.** Plates from other countries may show up as unconfirmed `Latin only` readings.
- **Trucks less than about 5 s apart** could have their plate and container paired wrongly.
  Each row's snapshot shows what was paired.
- **Blurry or very narrow vertical side codes** are still missed (`code4`, `face2`). The
  best free fix is a better camera angle: face the rear doors and get at least 20 px of
  character height.
- **Direction comes from the camera**, not from vehicle movement.
- **Built-in widgets stay in English.** A few of Streamlit's own widgets (e.g. the
  "Drag and drop files here" box) aren't translated.
- **Fine-tuning:** to push accuracy further, fine-tune the PP-OCR models on your own gate
  footage. It's free on Google Colab or Kaggle GPUs.

## Development

```bash
python -m pytest        # unit tests + accuracy regression on images/
```

Troubleshooting (Windows): `DLL load failed while importing onnxruntime_pybind11_state`
happens when `pandas`/`pyarrow` is imported before `onnxruntime`. Import `src.recognizer`
first (as `app.py` does), or `pip install -U onnxruntime pyarrow`.

---

## بالعربية

**قارئ الحاويات واللوحات** يقرأ أرقام الحاويات (ISO 6346) ولوحات الشاحنات السعودية من الصور
والفيديو وكاميرات المراقبة، ويسجّل كل شاحنة تدخل أو تخرج من البوابة في ملف Excel مع التاريخ
والوقت والاتجاه ورقم اللوحة (لاتيني وعربي) ورقم الحاوية والكاميرا والموقع وصورة للشاحنة وصورة للوحة.
مجاني بالكامل ويعمل على المعالج العادي.

- **التجربة:** https://container-gate-ocr.streamlit.app/ (اختر «العربية» أعلى القائمة الجانبية)
- **التشغيل على الكاميرات:** انسخ `cameras.example.json` إلى `cameras.json`، وضع
  `"language": "ar"` لسجل Excel بالعربية، ثم شغّل `python cctv.py --config cameras.json`
- **تحقق اللوحة:** يُقرأ السطر اللاتيني ثم السطر العربي، وعند تطابقهما تظهر «مطابق عربي ولاتيني»
- **لا تفتح ملف السجل في Excel أثناء التشغيل**، فالصفوف تُحفظ مؤقتاً وتُكتب بعد إغلاقه
