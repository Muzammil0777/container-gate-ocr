# Tasks: Gate lanes (multi-camera + ANPR) and licensing

See [plan.md](plan.md) for the design, risks and open questions.
Previous tasks (React app, done): [archive/todo-react-app.md](archive/todo-react-app.md).

Checks used below:
- **Tests:** `py -3.12 -m pytest`
- **Build:** `cd web && npm run build` (commit `web/dist` after any `web/src` change)
- **Run:** `py -3.12 server.py --open` and `py -3.12 cctv.py --config cameras.json`

---

## Phase 0: Evidence first

### Task 1: Multi-camera speed test on this laptop ✅
**Description:** Extend `bench.py` to replay several recordings at the same time through the
real pipeline (shared OCR lock, reading areas, follow mode), like 2-3 live cameras per lane.
Report looks per second per camera and trucks found, for 1, 2, 3 and 4 streams.

**Acceptance criteria:**
- [x] `bench.py a.mp4 b.mp4` (or `--copies N`) runs them together and prints looks/s per stream
- [x] Numbers recorded in plan.md for this laptop, with a recommendation (looks/s,
      reading areas, which cameras can share the CPU, hardware)

**Verification:** run on the recordings from Open Question 2 in plan.md (or existing ones until then).
**Dependencies:** None. **Files:** `bench.py`, `tasks/plan.md`. **Scope:** S

### Task 2: ANPR camera test (real camera)
**Description:** Connect to the ANPR camera, confirm it reads Saudi plates, and capture a few
real plate events (event text + plate photo) from its ISAPI event stream into
`tests/fixtures/anpr/` (passwords removed). Decide: camera's own reading (b) or ours (a).

**Acceptance criteria:**
- [ ] At least 3 real events saved, including night/IR if possible
- [ ] Plate text format documented (how Arabic letters/digits arrive)

**Verification:** saved files open and match what the camera's web page shows.
**Dependencies:** the camera on the network. **Files:** `tests/fixtures/anpr/`, `tasks/plan.md`. **Scope:** S

### Checkpoint: Decide hardware and ANPR mode
- [ ] You choose hardware and ANPR mode based on Tasks 1-2

---

## Phase 1: Lane foundation

### Task 3: Database: verification and lane columns ✅
**Description:** Add columns `lane`, `cams_agree` (container cameras that agreed),
`cams_expected`, `plate_source` (`anpr` / `ocr`), `snapshot2` (second angle). Existing
databases get them on start (additive `ALTER TABLE`). `needs_review` also flags a container
read by fewer cameras than expected. Excel and ZIP get a *Verified* column and the 2nd photo.

**Acceptance criteria:**
- [x] A database file from the current version opens, upgrades, and keeps every row
- [x] Excel shows *Verified by 2 cameras* / *1 camera only*; single-camera lanes look as today
- [x] Merging and deduplication (`Store.add`) unchanged for single-camera sites

**Verification:** tests: upgrade a saved old-format database; Excel column; needs_review cases.
**Dependencies:** None. **Files:** `src/store.py`, `src/i18n.py`, `src/gate.py`, `server.py` (2nd photo path hidden), `tests/test_store.py`, `tests/test_server.py`. **Scope:** M

### Task 4: Settings: lanes and camera roles ✅
**Description:** `cameras.json` cameras get `lane` and `role`; `lanes` holds direction and
location. `src/lanes.py` (not `src/config.py`: that imports `cctv.py`, which will need lanes) has `lanes(cfg)` returning each lane with its cameras; a camera
without a lane is its own lane with role `both`.

**Acceptance criteria:**
- [x] Today's `cameras.json` gives exactly today's behaviour (one lane per camera)
- [x] Invalid combinations are reported in plain words (e.g. a lane with no camera that reads plates)

**Verification:** tests for old settings, a 3-camera lane, invalid cases.
**Dependencies:** None. **Files:** `src/lanes.py`, `src/i18n.py` (problem texts), `tests/test_lanes.py`. **Scope:** S

### Task 5: Lane tracker: one truck from several cameras (test-driven) ✅
**Description:** `LaneTracker` in `src/gate.py` takes reads from all cameras of a lane
(camera, role, time, codes, plates, frame) and emits one event per truck: container by
consensus over all container cameras, `cams_agree`, plate from plate cameras (or an ANPR
event, already confirmed), best photo per camera. Reuses `_Groups`, `consensus_code`,
`_same_plate`. Thread-safe (cameras run in separate threads).

**Acceptance criteria:**
- [x] Both cameras read the same code: one event, `cams_agree = 2`
- [x] One camera misses a digit, the other reads it: correct code, verified when the
      check digit and the other camera agree
- [x] Plate first, container 20 s later: one event; container only / plate only: one event,
      not verified; a different plate while the visit has one: two trucks
- [x] Existing `GateTracker` tests still pass (single-camera lanes use the same rules)

**Verification:** 10 tests written first (failing), then the code; a single-camera lane was checked to give exactly GateTracker's events on today's scenarios, after which GateTracker became a lane of one camera (one implementation; today's tests unchanged and passing). `cams_agree` counts cameras that read the final number exactly at least once. Real misreads (`logs/corrections.jsonl`) to add once a site has them.
**Dependencies:** Task 3 (event fields). **Files:** `src/gate.py`, `tests/test_lane.py`. **Scope:** M

### Checkpoint: Lane logic
- [ ] Tests pass; code-reviewer agent review of Tasks 3-5; you review the rules

---

## Phase 2: Detection service

### Task 6: Service runs cameras by lane
**Description:** `cctv.py`: camera threads feed their lane's `LaneTracker` instead of their
own tracker; the lane logs one row with every camera's photo. Live status per camera
unchanged. Reloading settings restarts only the lanes that changed.

**Acceptance criteria:**
- [ ] Two synthetic videos of the same truck from two angles (one with a hidden digit) give
      one row, verified by 2 cameras
- [ ] A single-camera site gives exactly the rows it gives today (`tests/test_live.py`)

**Verification:** new live test with two videos; existing tests; replay real recordings.
**Dependencies:** Tasks 4, 5. **Files:** `cctv.py`, `src/gate.py`, `tests/test_live.py`. **Scope:** M

### Task 7: Hikvision ANPR events as the plate source (if Task 2 succeeds)
**Description:** `src/anpr.py`: listens to the camera's ISAPI event stream (digest login,
standard library only), turns each plate event into a confirmed plate (Latin + Arabic, our
format) with its plate photo, and feeds the lane. Reconnects like video streams do.

**Acceptance criteria:**
- [ ] The saved real events from Task 2 parse to the right plates
- [ ] A dropped connection reconnects; camera offline shows on Live like other cameras

**Verification:** tests on the fixtures; manual run against the real camera.
**Dependencies:** Tasks 2, 6. **Files:** `src/anpr.py`, `cctv.py`, `tests/test_anpr.py`. **Scope:** M

### Checkpoint: End to end with real recordings
- [ ] Real recordings replayed: rows match what a person sees in the videos; speed acceptable

---

## Phase 3: App

### Task 8: Cameras page: lanes and what each camera reads
**Description:** Camera form gets *Lane* and *What does this camera read?* (container / plate /
both, with a plain explanation and an (i)); lanes list with direction and location; Live
groups camera cards by lane. API: settings and camera endpoints carry `lane`, `role`, `lanes`.

**Acceptance criteria:**
- [ ] A 3-camera lane can be set up without editing files
- [ ] Old single-camera setups show and work as before
- [ ] English and Arabic, phone width

**Verification:** API tests; browser check on a test copy with the fake recorder.
**Dependencies:** Task 4. **Files:** `server.py`, `web/src/pages/Cameras.tsx`, `web/src/components/AddCamera.tsx`, `web/src/pages/Live.tsx`, `src/i18n.py`. **Scope:** M

### Task 9: Records and Excel: verified badge, every camera's photo
**Description:** Table and panel show *Verified by 2 cameras* (or *1 camera only* as a Check
reason); the panel shows both container angles and the plate photo. Photos endpoint serves
`snapshot2` by record id like the others.

**Acceptance criteria:**
- [ ] Each Check row says why (plate not confirmed / container not confirmed / only 1 camera)
- [ ] ZIP and Excel links include every photo

**Verification:** API tests for the new photo; browser check in both languages.
**Dependencies:** Tasks 3, 6. **Files:** `server.py`, `web/src/components/TruckDetail.tsx`, `web/src/components/TruckTable.tsx`, `src/i18n.py`. **Scope:** M

### Task 10: Setup wizard: second container camera and plate camera
**Description:** After the first camera, the wizard offers *Add the second container camera
for this gate* and *Add the plate camera*, each with the channel pictures; both can be skipped.

**Acceptance criteria:**
- [ ] A full lane (3 cameras) can be set up from the wizard alone
- [ ] Skipping gives a working single-camera lane

**Verification:** browser walk-through on a fresh test copy.
**Dependencies:** Task 8. **Files:** `web/src/pages/Setup.tsx`, `src/i18n.py`. **Scope:** S

### Checkpoint: Lanes complete
- [ ] Tests and build pass; code review; you try it on the site laptop with the real cameras

---

## Phase 4: License in the app

### Task 11: License check (test-driven) ✅
**Description:** `src/license.py`: verify a key (Ed25519, public key in the app, key id for
rotation), machine code from the Windows machine ID, states (trial (14 days from first start) /
active / expiring (30 days before) / grace (14 days after) / expired / no license after trial)
and the clock guard (latest time seen, kept in the database).

**Acceptance criteria:**
- [x] A changed character, another machine's key, or an expired key are refused with a plain reason
- [x] States change on the right days (30 days before, end date, end of grace)
- [x] Clock set back by a week: still counts from the latest time seen

**Verification:** 17 tests written first (failing), with keys made by a test-only key pair. Stored in a new `meta` table in gate.db (key, trial start, latest time seen). `PUBLIC_KEYS` is empty until Task 12 makes your real key pair.
**Dependencies:** None (can start in parallel with Phase 1). **Files:** `src/license.py`, `src/store.py` (meta table), `tests/test_license.py`, `requirements.txt`. **Scope:** M

### Task 12: Your license tool
**Description:** `tools/license_tool.py`: `keygen` (once; private key saved outside the repo),
`issue --customer --site --machine CODE --days 365 [--cameras N]` prints the key and adds it to
a local ledger, `inspect KEY` shows what is inside.

**Acceptance criteria:**
- [ ] Keys it issues are accepted by Task 11; a test fails if a private key file is ever inside the repo
- [ ] Clear instructions printed for backing up the private key

**Verification:** tests (issue, inspect, round trip); dry run.
**Dependencies:** Task 11. **Files:** `tools/license_tool.py`, `tests/test_license_tool.py`, `.gitignore`. **Scope:** S

### Task 13: Activation screen, License card, expiry banners
**Description:** API: `GET /api/license` (state, end date, days left, machine code),
`POST /api/license` (paste a key). App: activation screen when there's no license (after the
trial, if any), a License card on the Cameras page, banners from 30 days before with your
contact details.

**Acceptance criteria:**
- [ ] Machine code shown with a copy button; a pasted key activates at once
- [ ] Banners in English and Arabic; wrong keys get plain messages

**Verification:** API tests; browser check of each state (keys made by the test key pair).
**Dependencies:** Tasks 11, 12. **Files:** `server.py`, `web/src/pages/License.tsx`, `web/src/App.tsx`, `src/i18n.py`, `tests/test_server.py`. **Scope:** M

### Task 14: After the grace period
**Description:** When the license has run out (after grace), the detection service stops
reading cameras and the app refuses new cameras and video tests. Records, photos,
corrections and downloads keep working. A new key restarts detection within a minute.

**Acceptance criteria:**
- [ ] Expired: no new rows; existing rows, Excel and ZIP still available
- [ ] Renewed key: detection resumes without restarting the computer

**Verification:** tests with a short-lived test key; manual run.
**Dependencies:** Task 13. **Files:** `cctv.py`, `server.py`, `tests/test_license_enforce.py`. **Scope:** S

### Checkpoint: Licensing works offline
- [ ] Tests pass; security-auditor agent review of Tasks 11-14; you issue a real key with your tool

---

## Phase 5: Remote license control

### Task 15: License server
**Description:** `license_server/` (separate small FastAPI app, own SQLite): `POST /v1/checkin`
(license id, machine code, app version) answers active / ended plus a newer key if you renewed;
admin commands (renew, end, list) protected by an admin token. Holds the private key as a
secret setting, never in the repo.

**Acceptance criteria:**
- [ ] Renew: next check-in returns the new key; End: next check-in returns ended
- [ ] Wrong admin token refused; check-ins rate-limited

**Verification:** tests with FastAPI's test client.
**Dependencies:** Task 12. **Files:** `license_server/app.py`, `license_server/tests/test_app.py`, `license_server/README.md`. **Scope:** M

### Task 16: App checks in daily
**Description:** The detection service checks in once a day when online (5 s timeout, never
blocks or slows the gate), saves a newer key, and applies an "ended" answer. The License card
shows the last check-in.

**Acceptance criteria:**
- [ ] No internet / server down: nothing changes, no errors on screen
- [ ] Renewed on the server: the site shows the new end date within a day (or at once with *Check now*)

**Verification:** tests against a local license server; manual.
**Dependencies:** Tasks 14, 15. **Files:** `src/license.py`, `cctv.py`, `web/src/pages/License.tsx`. **Scope:** S

### Task 17: Put the license server online
**Description:** Deploy `license_server/` to the host you choose (HTTPS), set the private key
and admin token as secrets, and renew a test site from your laptop.

**Acceptance criteria:**
- [ ] HTTPS only; secrets not in the repo or logs
- [ ] A test site picks up a remote renewal

**Verification:** end-to-end renewal; `license_server/README.md` steps followed exactly.
**Dependencies:** Task 16, your hosting account. **Files:** `license_server/README.md`. **Scope:** S

### Checkpoint: Remote renewal works
- [ ] Renew and end a test license remotely; app unaffected while the server is down

---

## Phase 6: Release

### Task 18: Security review of licensing
**Description:** security-auditor agent reviews `src/license.py`, `tools/`, `license_server/`
and the app's license endpoints; fix every confirmed finding.

**Acceptance criteria:**
- [ ] No high or medium findings left open
**Verification:** review report; tests for each fix.
**Dependencies:** Task 17. **Scope:** S

### Task 19: README for sites, renewal guide for you
**Description:** README: lanes and camera roles, ANPR setup, what customers see before and
after the license end date. A private guide for you: making keys, renewing, moving a site to
a new computer, backing up the private key.

**Acceptance criteria:**
- [ ] A new site can be set up with lanes and activated from the README alone
**Verification:** walk through on a fresh copy.
**Dependencies:** all. **Files:** `README.md`, `license_server/README.md`. **Scope:** S

### Checkpoint: Complete
- [ ] All acceptance criteria met, tests and build pass
- [ ] Reviewed by you
