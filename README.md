# Container Gate OCR

Reads **shipping-container codes** (ISO 6346, e.g. `MRSU 786939 5  45G1`) and **Saudi number
plates** (e.g. `3231 UTA` / `و ط ا ٣٢٣١`) from live CCTV cameras, and logs every truck entering
or leaving a gate: date, time, direction, plate (Latin and Arabic), container code, camera,
location, a snapshot and a plate close-up. Records are reviewed and corrected in the app, and
downloaded as Excel per day or per month, or as a ZIP with photos. English and Arabic.

The app opens in a web browser, on the gate computer and on any computer or phone on the site
network (with the site password). Each site runs its own copy.

Everything is free and runs on a normal Windows laptop CPU: no GPU, no cloud, no paid API.

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
5. **Start:** double-click `start_gate.bat`. It starts the detection service (minimised
   window) and opens the app in the browser at http://localhost:8000. Keep the black
   *Gate app* window open.
6. **The first time, the app walks you through setup:**
   1. choose a **site password**
   2. enter the recorder's (NVR) IP address, username and password
   3. tap the camera picture that shows the gate, then drag a box over where trucks pass

   Detection starts on the camera within seconds. Add more cameras on the **Cameras** page
   (see *Camera placement* below for what makes a good camera).
7. **Other computers and phones** on the same network: the *Gate app* window shows the
   address to type, e.g. `http://192.168.1.103:8000`. They sign in with the site password.
   If Windows asks whether Python may use the network, allow it on **private networks**.
   Until a site password is chosen, the app opens only on the gate computer itself.
8. **Optional:** double-click `install_autostart.bat` so everything starts when you sign in
   to Windows (no administrator rights needed). `uninstall_autostart.bat` undoes it.

Camera not showing up? `find_cameras.bat` checks the NVR connection, explains network vs.
login problems and saves a snapshot of every channel to `logs\scan\`.

## The app

| Page | What it's for |
|---|---|
| **Live** | Each camera's picture with its detections and a clear state (*Working*, *No picture for 20 s*, *Stopped*), today's counts and trucks as they're logged, and today's Excel. If detection isn't running, one button starts it. |
| **Records** | Pick a day and tap a truck to see its **plate close-up and snapshot next to its readings**. *Correct the reading* fixes a wrong plate or container; the Excel files update straight away. *Only trucks to check* lists readings to double-check. Downloads: Excel for the day, Excel + photos (ZIP), Excel for the month. |
| **Cameras** | Recorder (NVR) login, Excel language, cameras (add / switch off / delete), each camera's reading area drawn on its picture with a test read, and the site password. |
| **Test** | Try photos, a recorded video (played like a gate camera, with an Excel of what it found) or a stream address, plus advanced OCR settings. Nothing here goes into the records. |

The language switch (English / العربية) is at the top; Arabic turns the whole page right-to-left.
Terms like *check digit* have an (i) that explains them.

**Check:** shown when the plate wasn't confirmed by its Arabic row, the container's check
digit wasn't confirmed, or one of them is missing. **Fixed** marks rows a person corrected.
Corrections are also kept in `logs\corrections.jsonl` with the photo, for improving accuracy
later.

## Where the data is

| Path | What |
|---|---|
| `logs\gate.db` | The master record (SQLite database). Safe with several programs reading and writing, and survives power cuts. |
| `logs\excel\gate_log_YYYY-MM-DD.xlsx` | One Excel per day, rewritten after every truck |
| `logs\excel\gate_log_YYYY-MM.xlsx` | One Excel per month, for audits |
| `logs\snapshots\YYYY-MM-DD\` | Truck snapshot and plate close-up for every row |
| `cameras.json` | Settings, including the NVR password and the site password (stored only as a salted hash). Stays on this computer (git-ignored). |

Opening an Excel file in Excel while trucks are being logged is fine: the data is safe in
the database, and the file is updated as soon as Excel closes it.

## How it works

```
cameras ──► cctv.py (detection service) ──► logs\gate.db ──► Excel files
                 ▲   │                           │
     cameras.json│   └─► live frames + status ──►├─► server.py (API + web app) ◄── browsers on the site network
                 └────────── app writes settings ┘
```

- **The app** is `server.py` (FastAPI) serving an API and the React web app in `web/`. The
  built app (`web/dist`) is part of the repository, so sites need only Python, not Node.js.

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
- **Reading area:** on the Cameras page, drag a box over where trucks pass to skip sky and
  far-away parts of the picture. It's faster, and the area is read sharper.

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
| camera `roi` | whole frame | Reading area `[left, top, right, bottom]` as fractions, drawn on the camera picture in the app |

## Command line

| Command | What |
|---|---|
| `py -3.12 server.py --open` | Run the app (port 8000) and open it in the browser |
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
- **Windows DLL error:** if you see `DLL load failed while importing onnxruntime_pybind11_state`,
  another library (pandas/pyarrow did this) was imported before `onnxruntime`. The app avoids
  this by import order.
- **Plain HTTP on the site network:** the site password protects the app, but traffic isn't
  encrypted. Keep the app on the site's own network; for access from outside, use a VPN such
  as Tailscale rather than opening a port to the internet.

## Changing the web app (developers)

Only needed to change how the app looks or works. Needs Node.js 20 or newer.

```bash
cd web
npm install
npm run dev
```

`npm run dev` serves the app at http://localhost:5173 and passes API calls to `server.py`
(run it too). After changes, `npm run build` rebuilds `web/dist`; commit it, since sites use
the built app as it is. All text is in [src/i18n.py](src/i18n.py) (English and Arabic).

---

## بالعربية

**قارئ الحاويات واللوحات** يقرأ أرقام الحاويات ولوحات الشاحنات السعودية من كاميرات المراقبة،
ويسجّل كل شاحنة تدخل أو تخرج مع التاريخ والوقت والاتجاه ورقم اللوحة (لاتيني وعربي) ورقم الحاوية
وصورة للشاحنة وصورة للوحة. مجاني ويعمل على معالج الجهاز.

- **التثبيت:** ثبّت Python 3.12، ثم `py -3.12 -m pip install -r requirements.txt`
- **التشغيل:** انقر مرتين على `start_gate.bat`، فيفتح التطبيق في المتصفح. في المرة الأولى يرشدك
  التطبيق خطوة بخطوة: اختر كلمة مرور للموقع، ثم أدخل بيانات جهاز التسجيل، ثم اضغط على صورة الكاميرا
  التي ترى البوابة وحدد منطقة القراءة
- **الأجهزة الأخرى والهواتف:** افتح العنوان الظاهر في نافذة *Gate app* (مثل `http://192.168.1.103:8000`)
  وسجّل الدخول بكلمة مرور الموقع
- **السجلات:** من صفحة السجلات اضغط على أي شاحنة لعرض صورة اللوحة وصورة الشاحنة وتصحيح القراءة، ونزّل
  ملف Excel لليوم أو للشهر أو ملف ZIP مع الصور
- **التشغيل التلقائي:** انقر مرتين على `install_autostart.bat`
- **أهم عامل للدقة هو موقع الكاميرا:** كاميرا قريبة من مسار البوابة تُظهر اللوحة بعرض 150 بكسل على الأقل
