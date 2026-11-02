# Container Gate OCR

Reads **shipping-container codes** (ISO 6346, e.g. `MRSU 786939 5  45G1`) and **Saudi number
plates** (e.g. `3231 UTA` / `و ط ا ٣٢٣١`) from live CCTV cameras, and logs every truck entering
or leaving a gate: date, time, direction, plate (Latin and Arabic), container code, camera,
location, a snapshot and a plate close-up. Records are reviewed and corrected in the app, and
downloaded as Excel per day or per month, or as a ZIP with photos. English and Arabic.

The app opens in a web browser, on the gate computer and on any computer or phone on the site
network (each person signs in with their own username). Each site runs its own copy.

Everything is free and runs on a normal Windows laptop CPU: no GPU, no cloud, no paid API.

![Output example](./output.jpg?raw=true "Output example")

## Install on a site PC

Before the install day, the site's IT prepares the PC, cameras and network with
[docs/it-checklist.md](docs/it-checklist.md). Gate staff get [docs/user-guide.md](docs/user-guide.md)
(English and Arabic); support contacts are in [docs/support.md](docs/support.md).

1. On the gate PC, signed in as an administrator, run `ContainerGateOCR-site-<version>-setup.exe`
   (made with `installer/build.py`, see *Building the installer* below). Nothing else is needed:
   Python, the OCR models and the web app are inside.
2. It installs to `C:\Program Files\Container Gate OCR`, starts the gate with the PC (Task Scheduler,
   *Container Gate OCR*: no one needs to sign in), opens port 8000 to the site network (private
   and domain networks only) and opens the app at http://localhost:8000. The desktop icon
   **Gate app** opens it again.
3. **The first time, the app walks you through setup:**
   1. choose the **admin password** (username `admin`)
   2. enter the recorder's (NVR) IP address, username and password
   3. tap the camera picture that shows the gate, then drag a box over where trucks pass

   Detection starts on the camera within seconds. Then set up lanes (below) on the **Cameras**
   page, and add a user for each gate staff member on the **Users** page.
4. **Activate:** the **License** page shows this PC's **machine code**. Send it to us, and paste the
   license key we send back on the same page. Until then the 14-day free trial runs.
5. **Other computers and phones** on the site network open `http://<gate PC address>:8000` (give
   the PC a fixed address on the router) and sign in with their username. Until the admin
   password is chosen, the app opens only on the gate PC itself.

Upgrading: run the new `setup.exe`; records and settings stay. Uninstalling keeps `logs\` and
`cameras.json` too.

Camera not showing up? In the app folder, `python\python.exe cctv.py --scan --config cameras.json`
checks the NVR connection, explains network vs. login problems and saves a snapshot of every
channel to `logs\scan\`.

### Building the installer (vendor)
Needs Python 3.12 and [Inno Setup 6](https://jrsoftware.org/isdl.php) on your PC. In the project folder:

```powershell
$env:GATE_SIGN_THUMBPRINT = "<your code-signing certificate's thumbprint>"   # leave out for an unsigned test build
py -3.12 installer/build.py --control-center https://cc.<your-domain>/v1/checkin   # --edition enterprise for Enterprise
```

The result is `installer\dist\ContainerGateOCR-site-<VERSION>-setup.exe`. A Site installer leaves
out `src/enterprise/`. The certificate stays in the Windows certificate store or on its USB token,
never in the repo; signing needs `signtool.exe` from the Windows SDK. `--stage-only` builds the
app folder in `installer\build\` without the installer, to try it first. Before building
installers for customers, `PUBLIC_KEYS` in `src/license.py` must hold your real public key.

## Run the app from a terminal (developers, or a PC without the installer)

Install **Python 3.12** (3.13 or newer will **not** work: the OCR package supports up to 3.12),
get the project (`git clone https://github.com/Muzammil0777/container-gate-ocr.git`), and in
the project folder:

```bash
py -3.12 -m pip install -r requirements.txt
```

`start_gate.bat` starts both parts below (`install_autostart.bat`: at Windows sign-in). To run
them yourself:

**Terminal 1, the app** (stop it with Ctrl+C):

```bash
py -3.12 server.py --open
```

It opens http://localhost:8000 in the browser and prints the address for other computers and
phones. `--port 8001` uses another port; leave out `--open` to not open the browser.

**Terminal 2, detection** (optional: the **Start detection** button on the Live page starts it too):

```bash
py -3.12 cctv.py --config cameras.json
```

It reads the cameras you set up in the app; without any cameras it simply waits. Without a
recorder you can still try everything on the **Test** page (sample photos, a video file).

Node.js is **not** needed to run the app: the built web app (`web/dist`) is in the repository.

## The app

| Page | What it's for |
|---|---|
| **Live** | Each camera's picture with its detections and a clear state (*Working*, *No picture for 20 s*, *Stopped*), today's counts and trucks as they're logged, and today's Excel. If detection isn't running, one button starts it. |
| **Records** | Pick a day and tap a truck to see its **plate close-up and snapshot next to its readings**. *Correct the reading* fixes a wrong plate or container; the Excel files update straight away. *Only trucks to check* lists readings to double-check. Downloads: Excel for the day, Excel + photos (ZIP), Excel for the month. |
| **Cameras** | Recorder (NVR) login, Excel language, lanes, cameras (add / switch off / delete, lane and role), each camera's reading area drawn on its picture with a test read. |
| **Test** | Try photos, a recorded video (played like a gate camera, with an Excel of what it found) or a stream address, plus advanced OCR settings. Nothing here goes into the records. |
| **Users** | Who can sign in and what they can do: *View* (records, Excel), *Operate* (+ live, fixes), *Admin* (+ cameras, settings, users, license). |
| **License** | State and end date, users and lanes used, the machine code, the key, and the last check-in with us. |

The language switch (English / العربية) is at the top; Arabic turns the whole page right-to-left.
Terms like *check digit* have an (i) that explains them.

**Check:** shown when the plate wasn't confirmed by its Arabic row, the container's check
digit wasn't confirmed, or one of them is missing. **Fixed** marks rows a person corrected.
Corrections are also kept in `logs\corrections.jsonl` with the photo, for improving accuracy
later.

## Lanes and camera roles

A **lane** is one way through the gate, e.g. *Entry* (trucks IN) or *Exit* (OUT). Put the cameras
that see the same truck in one lane: each truck is then logged **once**, with plate and container
paired by time and checked by every camera of the lane. Without lanes, each camera logs trucks
on its own.

On the **Cameras** page: *Add a lane* (name, IN or OUT), then for each camera choose its lane and
what it reads:

| Role | The camera sees | Typical |
|---|---|---|
| **Plate** | the number plate | one per lane, facing incoming trucks |
| **Container** | the container code | up to two per lane, from different sides |
| **Both** | both | a single camera that sees both |

When two cameras read the same container number, the row is marked **Verified by 2 cameras**.
The license sets how many lanes you can add (2 in the trial); for more, contact us.

## ANPR cameras

A Hikvision ANPR (LPR) camera works today as a normal **Plate** camera: connect it to the NVR, add
its channel on the Cameras page and give it the role *Plate*. Set it up for a sharp plate: the
plate at least 150 px wide, a short shutter (1/1000 s or faster) against motion blur, infrared on
at night. Taking the plate from the camera's own ANPR result instead of our OCR (no CPU cost on
the gate PC) is planned (Task 7) after the camera test (Task 2).

## License: before and after the end date

| When | The site sees | Cameras |
|---|---|---|
| First 14 days, no key yet | *Free trial* with the days left | read |
| Key active | *Active*, the end date, users and lanes used | read |
| 30 days before the end | *Ending soon* | read |
| End date to 14 days after | *Ended: extra days*, and a banner: the cameras stop in *n* days | read |
| After that | *Ended*: "the cameras are not being read" | **not read** |

Records, Excel and downloads keep working in every state: a site never loses its
data. A renewed key (picked up by itself within 15 minutes when the PC has internet, or pasted on
the License page) starts reading the cameras again. A key works only on the PC whose machine
code it was made for.

## Where the data is

On an installed site these are in `C:\Program Files\Container Gate OCR`. Back up `logs\`.

| Path | What |
|---|---|
| `logs\gate.db` | The master record (SQLite database). Safe with several programs reading and writing, and survives power cuts. |
| `logs\excel\gate_log_YYYY-MM-DD.xlsx` | One Excel per day, rewritten after every truck |
| `logs\excel\gate_log_YYYY-MM.xlsx` | One Excel per month, for audits |
| `logs\snapshots\YYYY-MM-DD\` | Truck snapshot and plate close-up for every row |
| `cameras.json` | Settings, including the NVR password. Stays on this computer (git-ignored). Users and their passwords (salted hashes) are in `logs\gate.db`. |

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
- **Plain HTTP on the site network:** sign-in protects the app, but traffic isn't
  encrypted. Keep the app on the site's own network; for access from outside, use a VPN such
  as Tailscale rather than opening a port to the internet.

## Changing the web app (developers)

Only needed to change how the app looks or works. Needs Node.js 20 or newer.

**Terminal 1, the API** (from the project folder):

```bash
py -3.12 server.py
```

**Terminal 2, the web app with live reload** (once: `npm install`):

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173: changes to `web/src` show up straight away, and API calls go to
`server.py` on port 8000. When done, build and commit `web/dist`, since sites use the built
app as it is:

```bash
cd web
npm run build
```

All text is in [src/i18n.py](src/i18n.py) (English and Arabic); restart `server.py` after
changing it. `py -3.12 -m pytest` runs the tests.

---

## بالعربية

**قارئ الحاويات واللوحات** يقرأ أرقام الحاويات ولوحات الشاحنات السعودية من كاميرات المراقبة،
ويسجّل كل شاحنة تدخل أو تخرج مع التاريخ والوقت والاتجاه ورقم اللوحة (لاتيني وعربي) ورقم الحاوية
وصورة للشاحنة وصورة للوحة. مجاني ويعمل على معالج الجهاز.

- **التثبيت:** شغّل `setup.exe` على جهاز البوابة بصلاحيات المسؤول. يبدأ التطبيق مع تشغيل الجهاز
  ويفتح في المتصفح. في المرة الأولى يرشدك التطبيق خطوة بخطوة: اختر كلمة مرور المسؤول (اسم المستخدم
  `admin`)، ثم أدخل بيانات جهاز التسجيل، ثم اضغط على صورة الكاميرا التي ترى البوابة وحدد منطقة القراءة.
  تجهيز الجهاز والشبكة: [docs/it-checklist.md](docs/it-checklist.md)، ودليل الموظفين: [docs/user-guide.md](docs/user-guide.md)
- **المسارات:** المسار ممر واحد عبر البوابة (دخول أو خروج). ضع فيه الكاميرات التي ترى الشاحنة نفسها:
  كاميرا للوحة وحتى كاميرتين للحاوية، فتُسجَّل كل شاحنة مرة واحدة
- **التفعيل:** أرسل لنا **رمز الجهاز** من صفحة الترخيص، والصق المفتاح الذي نرسله في الصفحة نفسها
- **بعد تاريخ الانتهاء:** 14 يوماً إضافية، ثم تتوقف قراءة الكاميرات. السجلات وملفات Excel تبقى تعمل دائماً
- **الأجهزة الأخرى والهواتف:** افتح `http://<عنوان جهاز البوابة>:8000` وسجّل الدخول باسم المستخدم
- **السجلات:** من صفحة السجلات اضغط على أي شاحنة لعرض صورة اللوحة وصورة الشاحنة وتصحيح القراءة، ونزّل
  ملف Excel لليوم أو للشهر أو ملف ZIP مع الصور
- **أهم عامل للدقة هو موقع الكاميرا:** كاميرا قريبة من مسار البوابة تُظهر اللوحة بعرض 150 بكسل على الأقل
