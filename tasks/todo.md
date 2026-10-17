# Tasks: React app for Container Gate OCR

See [plan.md](plan.md) for the architecture and decisions.

Checks used below:
- **Tests:** `py -3.12 -m pytest`
- **Build:** `cd web && npm run build`
- **Run:** `py -3.12 server.py` then open http://localhost:8000

---

## Phase 1: Foundation

### Task 1: Move shared helpers out of app.py ✅
**Description:** `load_config`, `save_config`, `service_status`, `start_service`, `grab_frame`
and saving a correction moved from `app.py` to `src/config.py` (not `src/site.py`: `site` is
the name of a built-in Python module). The correction check is `parse_fix` in `src/store.py`,
next to `Store.correct`. `app.py` imports them and behaves the same.

**Acceptance criteria:**
- [x] `app.py` has no copies of these helpers; Streamlit app works as before
- [x] Correction checking is one function: text in → fields to save, or error text keys
- [x] `tests/test_fix.py` covers good/bad plate, good/bad container, wrong check digit, empty fields, and saving (database + Excel + corrections log)

**Verification:** 58 tests pass; Streamlit app starts and Records renders with no errors.
**Dependencies:** None
**Files:** `src/config.py` (new), `src/store.py`, `app.py`, `tests/test_fix.py` (new)
**Scope:** S

### Task 2: API server and React shell ✅
**Description:** `server.py` (FastAPI) serves `/api/text`, `/api/health` and the built React
app from `web/dist`. `web/` is a Vite + React + TypeScript + Mantine app with a header (title,
English/العربية switch), four sections (Live, Records, Cameras, Test) as empty pages, and
right-to-left layout in Arabic. Language choice is remembered in the browser.

**Acceptance criteria:**
- [x] One command starts one server on one port that serves both the API and the app
- [x] All visible text comes from `src/i18n.py`; Arabic switches the whole layout right-to-left
- [x] OCR imports load without the onnxruntime DLL error under uvicorn on this laptop

**Verification:** Build passes; Run → shell visible, language switch works; `tests/test_server.py`
checks `/api/health` and `/api/text` with FastAPI's TestClient.
**Dependencies:** Task 1
**Files:** `server.py`, `requirements.txt`, `web/` (package.json, vite config, `src/main.tsx`, `src/App.tsx`, `src/api.ts` with the `useT()` text hook), `src/i18n.py`, `.gitignore` (web/dist is committed), `tests/test_server.py`
**Scope:** M

### Checkpoint: Foundation
- [ ] Tests pass, build passes, Streamlit app still works
- [ ] Review the look of the shell with the user before building pages

---

## Phase 2: Daily use

### Task 3: Live page
**Description:** Camera tiles with the live annotated image (refreshing every 2 s) and a clear
status per camera: green "Working", grey "Stopped", red "No picture for N s". If detection
isn't running, one big "Start detection" button. Below: today's counts (trucks, in, out,
need checking) and today's trucks, newest first, and "Download today's Excel".
API: `GET /api/status`, `GET /api/live/{camera}.jpg`, `POST /api/service/start`,
`GET /api/records?day=`, `GET /api/excel/day/{day}`.

**Acceptance criteria:**
- [ ] A truck logged by `cctv.py` appears within ~3 s without reloading the page
- [ ] Camera offline / service stopped states are shown in plain words with colour + icon
- [ ] Downloaded Excel is identical to what `to_excel` produces today

**Verification:** Tests for the endpoints; manual: run `cctv.py --source videos/...` and watch trucks appear.
**Dependencies:** Task 2
**Files:** `server.py`, `web/src/pages/Live.tsx`, `web/src/components/TruckTable.tsx`, `tests/test_server.py`
**Scope:** M

### Task 4: Records page: browse a day, see photos
**Description:** Pick a day (calendar), "only trucks that need checking" switch, counts, and
the day's trucks. Clicking a truck opens a side panel with the snapshot, plate close-up and
details (plate in Latin and Arabic, container, check digit). Photos come from
`GET /api/records/{id}/snapshot` and `/plate_image`, looked up by id.

**Acceptance criteria:**
- [ ] Rows keep their order (oldest first) so a fixed row doesn't jump
- [ ] Missing photo shows a friendly message, not a broken image
- [ ] Photo endpoints only return files referenced by that record (no path in the URL)

**Verification:** Test: unknown id → 404, record without photo → 404; manual check in browser.
**Dependencies:** Task 3 (reuses TruckTable)
**Files:** `server.py`, `web/src/pages/Records.tsx`, `web/src/components/TruckDetail.tsx`, `tests/test_server.py`
**Scope:** M

### Task 5: Records page: fix a reading, downloads
**Description:** In the side panel: edit plate, container and direction, Save. Uses the
Task 1 check function; errors show next to the field in plain words. Saving rewrites the
day/month Excel and appends to `logs/corrections.jsonl` (same as today). Download buttons:
day Excel, day ZIP with photos, month Excel.
API: `PATCH /api/records/{id}`, `GET /api/excel/month/{month}`, `GET /api/zip/day/{day}`.

**Acceptance criteria:**
- [ ] Bad plate / bad container is refused with a clear message; nothing is saved
- [ ] Wrong check digit saves but warns
- [ ] After saving, the row shows ✏️ and the Excel file in `logs/excel` has the new value

**Verification:** Tests for PATCH (good, bad, wrong check digit) and that the Excel file is rewritten.
**Dependencies:** Task 1, Task 4
**Files:** `server.py`, `web/src/components/TruckDetail.tsx`, `web/src/pages/Records.tsx`, `tests/test_server.py`
**Scope:** M

### Checkpoint: Daily use
- [ ] Tests and build pass
- [ ] Live → Records → fix → download works end to end on this laptop
- [ ] Review with the user (look and wording) before Phase 3

---

## Phase 3: Setup and testing

### Task 6: Cameras page: NVR login, camera list
**Description:** NVR address, user, password, port and Excel language form; Save checks the
NVR is reachable first. List of cameras as cards: name, channel, In/Out, location, on/off
switch, delete (with "Are you sure?"). Password is never sent back to the browser (shown as ••••).
API: `GET/PUT /api/settings`, `PATCH/DELETE /api/cameras/{name}`.

**Acceptance criteria:**
- [ ] Unreachable NVR → "Can't reach 192.168.1.64. Check the cable." and nothing saved
- [ ] `GET /api/settings` never contains the password; leaving it blank keeps the old one
- [ ] Switching a camera off stops it in `cctv.py` within a few seconds

**Verification:** Tests for settings (password hidden, blank keeps old), camera toggle/delete.
**Dependencies:** Task 2
**Files:** `server.py`, `web/src/pages/Cameras.tsx`, `tests/test_server.py`
**Scope:** M

### Task 7: Add camera: draw the reading area, test the camera
**Description:** "Add camera" form (name, channel, In/Out, location). Instead of four
sliders, the user clicks "Get picture", sees the camera's current frame and **drags a box**
over where trucks pass. "Test" button runs OCR on one frame and shows what it read.
API: `POST /api/cameras`, `POST /api/cameras/frame` (grab one frame), `POST /api/ocr` (image → result + annotated image).

**Acceptance criteria:**
- [ ] Drawn box is saved as the same `roi` fractions `cctv.py` reads today
- [ ] Without drawing a box, the whole picture is used
- [ ] Test result shows the annotated picture plus container/plate found, or "Nothing found"

**Verification:** Test that `roi` is stored correctly; manual with the NVR (or a video file source).
**Dependencies:** Task 6
**Files:** `server.py`, `web/src/pages/Cameras.tsx`, `web/src/components/AreaPicker.tsx`, `web/src/components/OcrResult.tsx`
**Scope:** M

### Task 8: Test page: photos and stream URL
**Description:** Drop photos (or pick a sample from `images/`) → annotated picture, container
codes, plates, time taken. "Advanced" fold holds the OCR settings (max side, zoom, vertical,
plates). Stream URL → grab one frame → same result view. Reuses `OcrResult` from Task 7.
API: `POST /api/ocr` (upload, with options), `GET /api/samples`, `POST /api/stream/frame`.

**Acceptance criteria:**
- [ ] Several photos at once, each with its own result
- [ ] Not-an-image upload → friendly error
- [ ] Results match the Streamlit Test tab for the same sample image

**Verification:** Test `/api/ocr` with `demo_input.jpg` (finds the known code).
**Dependencies:** Task 7
**Files:** `server.py`, `web/src/pages/Test.tsx`, `tests/test_server.py`
**Scope:** S

### Task 9: Test page: video file as a background job
**Description:** Upload a video, choose looks/second, In/Out, location → "Process". The server
runs it in a background thread (same GateTracker/GateLog code as app.py today, in a temp
folder) and the page shows a progress bar and the latest frame, then the trucks found with
their snapshots and an Excel download.
API: `POST /api/video` → job id, `GET /api/video/{job}` (progress, frame, rows), `GET /api/video/{job}/excel`.

**Acceptance criteria:**
- [ ] Page stays usable while the video is processed; progress moves
- [ ] Same trucks found as the Streamlit Test tab for the same video
- [ ] Test runs don't touch the real `logs/gate.db`

**Verification:** Test with a short clip from `videos/` (or skip if none present); manual run.
**Dependencies:** Task 8
**Files:** `server.py`, `web/src/pages/Test.tsx`
**Scope:** M

### Checkpoint: Feature parity
- [ ] Tests and build pass
- [ ] Walk through every Streamlit tab and do the same in React
- [ ] Review with the user

---

## Phase 4: For non-technical users, and roll-out

### Task 10: First-run setup wizard and plain-language help
**Description:** When there's no NVR or camera yet, open a 3-step wizard instead of empty
pages: 1) connect to the recorder (IP, user, password, with a live "Connected ✓"), 2) add
the gate camera (pick channel from snapshots, In/Out, draw area), 3) done → Live page.
Every empty state says what to do next in one sentence. Help icons explain terms
("check digit", "reading area") in plain words. Big touch-friendly buttons; works on a phone.

**Acceptance criteria:**
- [ ] A person who has never seen the app sets up a camera without reading the README
- [ ] Usable at phone width (375 px) without sideways scrolling
- [ ] All new text exists in English and Arabic

**Verification:** Manual: delete `cameras.json`, start, follow the wizard; phone-width check in browser.
**Dependencies:** Task 7
**Files:** `web/src/pages/Setup.tsx`, `web/src/App.tsx`, `src/i18n.py`
**Scope:** M

### Task 11: Site login (one password per site)
**Description:** A site password set in the wizard (stored hashed in `cameras.json`). All
`/api/*` except login need a session cookie. Server binds to localhost until a password is
set, then to the network so other devices can open it.

**Acceptance criteria:**
- [ ] Without login, API returns 401 and the app shows the login screen
- [ ] Wrong password → message, with a short delay after repeated tries
- [ ] Password is never stored in plain text

**Verification:** Tests: 401 without cookie, 200 with, hash stored.
**Dependencies:** Task 10
**Files:** `server.py`, `src/config.py`, `web/src/pages/Login.tsx`, `tests/test_server.py`
**Scope:** M

### Task 12: Switch launchers, update README, remove Streamlit
**Description:** `start_gate.bat` starts the detection service and `server.py`, then opens the
browser. `install_autostart.bat` unchanged in spirit. README: new install steps, the
address other devices use (`http://<laptop-ip>:8000`), how to rebuild the web app. Delete
`app.py`, Streamlit from `requirements.txt`, the Streamlit `.claude/launch.json` entry
(replace with the new server). Remove the online demo link and badge from the README.

**Acceptance criteria:**
- [ ] Double-click `start_gate.bat` → browser opens the React app, detection runs
- [ ] No Streamlit code or dependency left 
- [ ] README install steps work on a clean Windows PC with only Python 3.12

**Verification:** Tests and build pass; fresh clone + README steps on this laptop.
**Dependencies:** Checkpoint: Feature parity
**Files:** `start_gate.bat`, `README.md`, `requirements.txt`, `app.py` (deleted), `.claude/launch.json`
**Scope:** S

### Checkpoint: Complete
- [ ] All acceptance criteria met, tests and build pass
- [ ] Ready for review
