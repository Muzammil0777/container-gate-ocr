# Container Gate OCR

Reads **shipping-container codes** (ISO 6346, e.g. `MRSU 786939 5  45G1`) and **Saudi number
plates** (e.g. `3231 UTA` / `و ط ا ٣٢٣١`) from live CCTV cameras, and logs every truck entering
or leaving a gate: date, time, direction, plate (Latin and Arabic), container code, camera,
location, a snapshot and a plate close-up. Records are reviewed and corrected in the app, and
downloaded as Excel per day or per month, or as a ZIP with photos. English and Arabic.

Everything is free and runs on a normal Windows laptop CPU: no GPU, no cloud, no paid API.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://container-gate-ocr.streamlit.app/)
**Online demo: https://container-gate-ocr.streamlit.app/** (Test tab: upload a photo of a truck).

![Output example](./output.jpg?raw=true "Output example")

## Install on the site laptop

1. Install **Python 3.12** from https://www.python.org/downloads/ (tick *Add python.exe to
   PATH*). Python 3.13 or newer will **not** work: the OCR package supports up to 3.12.
2. Get the project, either with `git clone https://github.com/Muzammil0777/container-gate-ocr.git`
   or with *Code → Download ZIP*.
3. In the project folder:

   ```bash
   py -3.12 -m pip install -r requirements.txt
   ```

4. Connect the laptop to the camera network. Use a cable to the NVR's LAN port or its switch;
   the Wi-Fi can stay on for internet. If the cable gives an address starting `169.254`, give
   the Ethernet port a fixed IP in the NVR's range.
5. **Find the cameras:** double-click `find_cameras.bat`. It asks for the NVR IP, username and
   password (hidden), checks the connection, and saves a snapshot of every channel to
   `logs\scan\`. Pick the channel that sees the trucks best (see *Camera placement* below).
6. **Start:** double-click `start_gate.bat`. It starts the detection service (minimised
   window) and opens the app at http://localhost:8502.
7. In the app's **📷 Cameras** tab:
   - enter the NVR IP, username and password
   - add each gate camera: channel, IN/OUT, location, and optionally a reading area
   - detection starts on it within seconds
8. **Optional:** double-click `install_autostart.bat` so everything starts when you sign in
   to Windows (no administrator rights needed). `uninstall_autostart.bat` undoes it.

## The app

| Tab | What it's for |
|---|---|
| 🔴 **Live** | Each camera's view with its detections (🟢 online / 🔴 offline warning), today's trucks as they're logged, and ⬇ today's Excel. If detection isn't running, a button starts it. |
| 📒 **Records** | Pick a day and click a truck to see its **snapshot and plate photo next to its details**. Fix a wrong plate or container and save; the Excel files update straight away. *Show only trucks that need review* lists readings to double-check. Downloads: **⬇ Excel (day)**, **📦 ZIP with photos (day)**, **⬇ Excel (month)**. |
| 📷 **Cameras** | NVR login, Excel language, cameras (add / change / switch off / delete), reading area, and a one-frame camera test. |
| 🧪 **Test** | Try a photo, a recorded video (simulates the gate and gives an Excel) or a stream URL, plus the OCR settings. |

**Needs review (⚠️):** shown when the plate wasn't confirmed by its Arabic row, the
container's check digit wasn't confirmed, or one of them is missing. ✏️ marks rows a person
corrected. Corrections are also kept in `logs\corrections.jsonl` with the photo, for
improving accuracy later.

## Where the data is

| Path | What |
|---|---|
| `logs\gate.db` | The master record (SQLite database). Safe with several programs reading and writing, and survives power cuts. |
| `logs\excel\gate_log_YYYY-MM-DD.xlsx` | One Excel per day, rewritten after every truck |
| `logs\excel\gate_log_YYYY-MM.xlsx` | One Excel per month, for audits |
| `logs\snapshots\YYYY-MM-DD\` | Truck snapshot and plate close-up for every row |
| `cameras.json` | Settings, including the NVR password. Stays on this computer (git-ignored). |

Opening an Excel file in Excel while trucks are being logged is fine: the data is safe in
the database, and the file is updated as soon as Excel closes it.

## How it works

```
cameras ──► cctv.py (detection service) ──► logs\gate.db ──► Excel files
                 ▲   │                           │
     cameras.json│   └─► live frames + status ──►├─► app.py (Streamlit): Live / Records / Cameras / Test
                 └────────── app writes settings ┘
```

- **Detection runs as its own service** (`cctv.py`), separate from the app. It follows
  `cameras.json` (cameras added or stopped in the app take effect within a second),
  reconnects dropped streams, refuses to run twice, and `run_service.bat` restarts it if it
  ever stops.
- **Search small, read sharp** ([src/recognizer.py](src/recognizer.py)): text is *found* on a
  downscaled frame, but each piece is *read* from the full-resolution 4K frame.
- **Follow what was found** ([src/scanner.py](src/scanner.py)): after a full scan finds a code
  or plate, the next looks only search small windows around it, which is cheaper. That gives
  more reads in the few seconds a truck is readable.
- **Containers** ([src/iso6346.py](src/iso6346.py)): `owner + U/J/Z + serial + check digit`.
  - A boxed check digit is re-read on its own.
  - Reads from several frames are **combined** (consensus), e.g. `MRSU 786395 ?` +
    `MRSU 786839 5` + `MRSU 786039 5` → **`MRSU 786939 5`** ✅. The check digit settles a
    single uncertain digit, and only among look-alikes.
- **Saudi plates** ([src/saudi_plate.py](src/saudi_plate.py)): the Latin row (`3231 UTA`) is
  read and checked against the Arabic row (`و ط ا ٣٢٣١`) with an Arabic model (PP-OCRv5).
  The 17 plate letters map one-to-one between Arabic and Latin.
- **One row per truck** ([src/gate.py](src/gate.py), [src/store.py](src/store.py)): plate and
  container are confirmed over several frames and logged together. A repeat within 5 minutes
  (same direction) never creates a second row; if the repeat adds a plate or a confirmed check
  digit, the earlier row is filled in instead.

## Accuracy and speed

`python -m pytest` checks the sample images in `images/`, including 3 real Saudi gate photos:
- **Containers:** 18 of 22 images give a check-digit-confirmed code, with 0 false codes.
- **Plates:** all 3 Saudi plates are read and confirmed by the Arabic row.

**On real CCTV footage**, use the benchmark. It plays a recording through the pipeline exactly
like a live camera, skipping frames while busy:

```bash
py -3.12 bench.py "C:\path\to\nvr_export.mp4" --realtime --follow --roi 0,0,0.66,0.78 --max-side 1600
```

| On a Ryzen 7 5800U laptop, wide-angle 4K yard camera | Before | Now |
|---|---|---|
| Looks per second | 0.34 | about 0.9 |
| Trucks logged (12 passes in 2 clips) | 0 | 2, both correct |
| Wrong rows | 0 | 0 |

## Camera placement (the biggest factor)

The software reads what the camera shows. A wide overview camera (like the yard camera
above) shows each truck's plate and code only for 1–3 seconds, and with characters about
20 px tall; that's why only a few trucks get logged. For reliable logging:

- **Plate:** a camera facing incoming trucks at the gate lane, 5–10 m away, zoomed so the
  plate is **at least 150 px wide** in the picture, with no motion blur. A Hikvision
  ANPR/LPR camera is ideal.
- **Container:** a camera that sees the container's rear doors (or side) from **under about 10 m**,
  so the code's characters are **at least 25–30 px tall**. Trucks usually stop at the barrier,
  which gives plenty of readable frames.
- The 3 test photos in `images/ksa_*.jpg` (taken behind the trucks) read perfectly. That's
  the view to aim for.
- **Reading area:** use the *Reading area* sliders (Cameras tab) to skip sky and far-away
  parts of the picture. It's faster, and the area is read sharper.

## Settings (`cameras.json`, all optional)

| Key | Default | Meaning |
|---|---|---|
| `language` | `en` | Excel headers and values: `en` or `ar` |
| `plates` | true | Read Saudi number plates |
| `fps` | 4 | Looks per second per camera, at most |
| `min_hits` | 2 | Reads needed to confirm a code/plate (2× for a container without a confirmed check digit) |
| `gap_s` / `max_wait_s` | 5 / 10 | When a truck's row is written if only one of plate/container was read |
| `cooldown_s` | 300 | The same truck isn't logged again in the same direction within this time |
| `max_side` | 1920 | Search size for whole frames (1600 when a camera has a reading area) |
| `use_cuda` | false | NVIDIA GPU: `pip install onnxruntime-gpu`, then `true` (built-in Intel/AMD graphics doesn't help) |
| camera `roi` | whole frame | Reading area `[left, top, right, bottom]` as fractions, set with the sliders in the app |

## Command line

| Command | What |
|---|---|
| `py -3.12 cctv.py --scan` | Find cameras on the NVR (asks for login) |
| `py -3.12 cctv.py --config cameras.json` | Run the detection service |
| `py -3.12 cctv.py --source video.mp4 --direction IN` | Log a single video or camera without the app |
| `py -3.12 bench.py video.mp4 --realtime --follow` | Benchmark a recording |
| `py -3.12 single_frame_process.py -i photo.jpg` | Read one photo |
| `py -3.12 -m pytest` | Tests |

## Known limitations

- **Saudi plates only.** Plates from other countries may appear as unconfirmed "Latin only" readings.
- **Close trucks:** trucks less than about 5 s apart could have plate and container paired
  wrongly. The snapshot shows what was paired, and it can be fixed in Records.
- **Built-in widgets stay in English:** a few of Streamlit's own widgets (the file upload box)
  aren't translated.
- **Windows DLL error:** if you see `DLL load failed while importing onnxruntime_pybind11_state`,
  `pandas`/`pyarrow` was imported before `onnxruntime`. The app avoids this by import order.

---

## بالعربية

**قارئ الحاويات واللوحات** يقرأ أرقام الحاويات ولوحات الشاحنات السعودية من كاميرات المراقبة،
ويسجّل كل شاحنة تدخل أو تخرج مع التاريخ والوقت والاتجاه ورقم اللوحة (لاتيني وعربي) ورقم الحاوية
وصورة للشاحنة وصورة للوحة. مجاني ويعمل على معالج الجهاز.

- **التثبيت:** ثبّت Python 3.12، ثم `py -3.12 -m pip install -r requirements.txt`
- **التشغيل:** انقر مرتين على `start_gate.bat`، ثم أضف جهاز التسجيل والكاميرات من تبويب 📷 الكاميرات
- **السجلات:** من تبويب 📒 السجلات اضغط على أي شاحنة لعرض صورتها وصورة اللوحة وتصحيح القراءة، ونزّل
  ملف Excel لليوم أو للشهر أو ملف ZIP مع الصور
- **التشغيل التلقائي:** انقر مرتين على `install_autostart.bat`
- **أهم عامل للدقة هو موقع الكاميرا:** كاميرا قريبة من مسار البوابة تُظهر اللوحة بعرض 150 بكسل على الأقل
