# Tasks: Gate lanes (multi-camera + ANPR) and licensing

See [plan.md](plan.md) for the design, risks and open questions.
Previous tasks (React app, done): [archive/todo-react-app.md](archive/todo-react-app.md).

Checks used below:
- **Tests:** `py -3.12 -m pytest`
- **Build:** `cd web && npm run build` (on `react-app` after merging; task branches don't commit `web/dist`)
- **Run:** `py -3.12 server.py --open` and `py -3.12 cctv.py --config cameras.json`

Phases are in build order (reordered 2026-10-28); task numbers stay as first planned.

## Parallel work: two sessions in Orca (added 2026-10-28)

Two Claude Code sessions, each in its own Orca worktree, each on its own branch from
`react-app`. Rules for the sessions: `CLAUDE.md`, "Parallel work". Each session owns a set of
files, so the two never edit the same file in a round:

- **Session A, "App":** `server.py`, `web/src/`, `src/store.py`, `src/i18n.py`, `src/license.py`,
  `src/config.py`, `src/checkin.py`, `tools/`.
- **Session B, "Engine and tools":** `cctv.py`, `src/gate.py`, the OCR files (`src/recognizer.py`,
  `src/scanner.py`, `src/iso6346.py`, `src/saudi_plate.py`), `src/lanes.py`, `src/camera.py`,
  `src/turnaround.py`, `bench.py`, `installer/`, `deploy/`, `docs/`, `README.md`, `VERSION`,
  `CHANGELOG.md`, and the whole Control Center repo (`gate-reader-control`).
- **Enterprise folders** (`src/enterprise/`, `web/src/enterprise/`): owned task by task, as the table says.
- Exceptions are named in the table (e.g. Task 14 edits `cctv.py`: session B is in the Control
  Center repo then).

| Round | Session A (App) | Session B (Engine and tools) | Needs from you |
|---|---|---|---|
| 1 | Task 8: Cameras page, lanes | Task 6: service runs cameras by lane | |
| 2 | Task 9: Records, verified badge, photos | Task 36: accuracy (yard parts; night when recordings come) | |
| 3 | Task 10: wizard, then Task 13: activation screen (test key pair) | Task 12: license tool (creates the Control Center repo) | a private GitHub repo |
| 4 | Task 20, then 21: users, login by username | Task 15: Control Center server | |
| 5 | Task 22, then 23: Users page, who fixed it | Task 40: Control Center pages | |
| 6 | Task 14 (also `cctv.py`), then 24: grace stop, license limits | Task 41, then 42: alerts, versions | |
| 7 | Task 25 (its tool options are in the Control Center repo), then 16: License card usage, heartbeat | Task 17: Control Center online (final check after Task 16 merges) | a Saudi VPS and a domain |
| 8 | Task 39: import old Excel logs | Task 33, then 35, then 19: installer, customer docs, README | code-signing certificate |
| - | Task 18: security review of the merged code (either session, fixes split by file) | | |
| 9 | Task 26, then 43: `updated_at` and the Enterprise hooks, Site manager role | Task 45: turnaround time | |
| 10 | Task 44: Site manager dashboard | Task 27: HQ receive API (`src/enterprise/`) | |
| 11 | Task 29: HQ mode pages (tested with rows sent through Task 27's API) | Task 28: site sync worker | |
| 12 | Task 31: HQ manager role and site scope | Task 30: Connect to HQ | |
| 13 | Task 46: HQ manager dashboard | Task 32: deploy HQ and restore test | a VPS for a test HQ |
| 14 | | Task 7 (ANPR), Task 37 (option 2) or Task 34, whichever is ready | ANPR camera / an option 2 customer |

Any time: **Task 2** (ANPR camera test) is yours; Task 7 follows in session B in any round where
session A isn't in `cctv.py` (not round 6). **Task 38** (option 2 build) touches both
sessions' files: split it by file after Task 37's design, when a customer chooses option 2.

**A round, step by step**
1. In Orca, make two worktrees from the latest `react-app`: branches `task/<n>-<short-name>`.
2. Start Claude Code in each with: *"Do Task N from tasks/todo.md. Follow CLAUDE.md, Parallel
   work."* (two tasks in a row: *"Do Task N, then Task M, one commit each."*)
3. When both are done, in the main folder on `react-app`: merge each branch, run
   `py -3.12 -m pytest`, then `cd web && npm run build` and commit `web/dist` ("Build web/dist").
4. Remove the two worktrees; start the next round from the new `react-app`.

A session that finishes early can take its next task only if it touches none of the other
session's current files.

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
- [x] Tests pass; code-reviewer agent review of Tasks 3-5 (2026-10-19). Fixed with a failing test
      first: a single camera reading a plate two ways made a phantom second truck (regression,
      now one truck again); the second container camera got no wait when the plate came first;
      photos copied twice; crash with 3 container cameras of equal score; a late camera thread
      moved the visit's clock back; a camera named like a lane joined it; two processes
      upgrading an old database at once
- [ ] You review the rules (one truck per lane visit, verified = both container cameras read
      the exact number at least once, waits: pair_window_s 30 s, max_wait_s 10 s)

---

## Phase 2: Detection service

### Task 6: Service runs cameras by lane ✅ (pairing check on real recordings still open)
**Description:** `cctv.py`: camera threads feed their lane's `LaneTracker` instead of their
own tracker; the lane logs one row with every camera's photo. Live status per camera
unchanged. Reloading settings restarts only the lanes that changed.

**Acceptance criteria:**
- [x] Two synthetic videos of the same truck from two angles (one with a hidden digit) give
      one row, verified by 2 cameras
- [x] A single-camera site gives exactly the rows it gives today (`tests/test_live.py`)

- [x] Snapshots: the container box drawn on the container photo, the plate box on the plate
      photo (today both are drawn on one frame; with lanes they come from different cameras)
- [ ] Pairing across trucks (from the review): a truck without a container followed by one
      whose plate wasn't read, and a next plate confirmed while the rear camera still reads the
      previous container: tested on real recordings; at least such rows are marked Check

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

### Task 36: Accuracy on real yard footage (yard parts ✅, night recordings still open)
**Description:** Fix what the 2.5K yard recording showed (2026-10-28) and test at night.
(1) Junk container codes next to the real one ('CAAU 250015 ?', 'DLAU161707?' from the door
markings), which once opened a junk row: find which pass makes them (zoom, vertical, stitched
fragments) before fixing. (2) Plates read from dark print on white containers (reefers): the
dark-on-light check only stops white paint on dark doors. (3) Night/IR recordings from the site
cameras.

**Acceptance criteria:**
- [x] The yard frames give only CAAU 987321 0, no extra codes, still 22/22
- [x] A marking on a white container is not a plate; the 3 real plates in images/ still read
- [ ] Night recording replayed: rows match what a person sees; misses listed in plan.md

**Verification:** tests from small saved crops under `tests/data/` (no full videos); replay with `bench.py`.
**Dependencies:** Task 6; night recordings (Open Question 2). **Files:** `src/recognizer.py`, `src/iso6346.py`, `tests/test_samples.py`. **Scope:** M

### Checkpoint: End to end with real recordings
- [ ] Real recordings replayed: rows match what a person sees in the videos; speed acceptable

---

## Phase 3: App

### Task 8: Cameras page: lanes and what each camera reads ✅
**Description:** Camera form gets *Lane* and *What does this camera read?* (container / plate /
both, with a plain explanation and an (i)); lanes list with direction and location; Live
groups camera cards by lane. API: settings and camera endpoints carry `lane`, `role`, `lanes`.

**Acceptance criteria:**
- [x] A 3-camera lane can be set up without editing files
- [x] Old single-camera setups show and work as before
- [x] English and Arabic, phone width

**Verification:** API tests; browser check on a test copy with the fake recorder.
**Dependencies:** Task 4. **Files:** `server.py`, `web/src/pages/Cameras.tsx`, `web/src/components/AddCamera.tsx`, `web/src/pages/Live.tsx`, `src/i18n.py`. **Scope:** M

### Task 9: Records and Excel: verified badge, every camera's photo ✅
**Description:** Table and panel show *Verified by 2 cameras* (or *1 camera only* as a Check
reason); the panel shows both container angles and the plate photo. Photos endpoint serves
`snapshot2` by record id like the others.

**Acceptance criteria:**
- [x] Each Check row says why (plate not confirmed / container not confirmed / only 1 camera)
- [x] ZIP and Excel links include every photo

**Verification:** API tests for the new photo; browser check in both languages.
**Dependencies:** Tasks 3, 6. **Files:** `server.py`, `web/src/components/TruckDetail.tsx`, `web/src/components/TruckTable.tsx`, `src/i18n.py`. **Scope:** M

### Task 10: Setup wizard: second container camera and plate camera ✅
**Description:** After the first camera, the wizard offers *Add the second container camera
for this gate* and *Add the plate camera*, each with the channel pictures; both can be skipped.

**Acceptance criteria:**
- [x] A full lane (3 cameras) can be set up from the wizard alone
- [x] Skipping gives a working single-camera lane

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

### Task 12: Your license tool ✅
**Description:** Creates the Control Center repo (`gate-reader-control`), private on GitHub, with its own `CLAUDE.md`.
`license_tool.py` there: `keygen` (once; private key saved outside the repo),
`issue --customer --site --machine CODE --days 365 [--cameras N]` prints the key and adds it to
a local ledger, `inspect KEY` shows what is inside.

**Acceptance criteria:**
- [x] Keys it issues are accepted by Task 11: a sample key made with the test key pair is saved in
      this repo's `tests/fixtures/license/`, and both repos test against it so the format can't drift
- [x] A test fails if a private key file is ever inside either repo
- [x] Clear instructions printed for backing up the private key

**Verification:** tests (issue, inspect, round trip); dry run.
**Dependencies:** Task 11. **Files:** Control Center repo: `license_tool.py`, `tests/`, `.gitignore`;
this repo: `tests/fixtures/license/`, `tests/test_license.py`. **Scope:** S

### Task 13: Activation screen, License card, expiry banners ✅
**Description:** API: `GET /api/license` (state, end date, days left, machine code),
`POST /api/license` (paste a key). App: activation screen when there's no license (after the
trial, if any), a License card on the Cameras page, banners from 30 days before with your
contact details.

**Acceptance criteria:**
- [x] Machine code shown with a copy button; a pasted key activates at once
- [x] Banners in English and Arabic; wrong keys get plain messages

**Verification:** API tests; browser check of each state (keys made by the test key pair).
**Dependencies:** Tasks 11, 12. **Files:** `server.py`, `web/src/pages/License.tsx`, `web/src/App.tsx`, `src/i18n.py`, `tests/test_server.py`. **Scope:** M

### Task 14: After the grace period ✅
**Description:** When the license has run out (after grace), the detection service stops
reading cameras and the app refuses new cameras and video tests. Records, photos,
corrections and downloads keep working. A new key restarts detection within a minute.

**Acceptance criteria:**
- [x] Expired: no new rows; existing rows, Excel and ZIP still available
- [x] Renewed key: detection resumes without restarting the computer

**Verification:** tests with a short-lived test key; manual run.
**Dependencies:** Task 13. **Files:** `cctv.py`, `server.py`, `tests/test_license_enforce.py`. **Scope:** S

### Checkpoint: Licensing works offline
- [ ] Tests pass; security-auditor agent review of Tasks 11-14; you issue a real key with your tool

---

## Phase 5: Named users and seats

### Task 20: Users table, upgrade from the site password ✅
**Description:** `users` table in `logs/gate.db` (username, name, password hash, role
`admin`/`operator`/`viewer`, active, created). Reuse `hash_password` / `check_password`. On
start, a site with `site_password` and no users gets user `admin` with that same hash.

**Acceptance criteria:**
- [x] An existing site logs in as `admin` with its old password, nothing else changes
- [x] Usernames unique (case-insensitive); passwords never stored or logged in plain text

**Verification:** tests (test-driven): upgrade from a saved old `cameras.json` + `gate.db`.
**Dependencies:** None. **Files:** `src/store.py`, `server.py`, `tests/test_users.py`. **Scope:** M

### Task 21: Login by username, roles on every route ✅
**Description:** `/api/login` takes username + password; the cookie carries the user id inside
the HMAC. A disabled user's cookie stops working at once. Each API route declares the lowest
role allowed (viewer: records, Excel; operator: + live, fixes; admin: + settings, cameras,
users, license).

**Acceptance criteria:**
- [x] Every route in `server.py` has a role; a test lists routes and fails on one without
- [x] Viewer can't fix or change settings (403); disabled user is logged out
- [x] Wrong-password slow-down still works per device

**Verification:** tests (test-driven); browser check in en/ar.
**Dependencies:** Task 20. **Files:** `server.py`, `web/src/pages/Login.tsx`, `src/i18n.py`, `tests/test_server.py`. **Scope:** M

### Task 22: Users page (admin) ✅
**Description:** Add, disable, reset password, change role. Shows "Users N of M" (M from the
license, Task 24; 5 until then). Plain text for staff, en/ar.

**Acceptance criteria:**
- [x] The last active admin can't be disabled or demoted
- [x] Over the limit: "Your license allows N users. Contact us to add 5 more."

**Verification:** browser check en/ar; tests for the API rules. Build and commit `web/dist`.
**Dependencies:** Task 21. **Files:** `web/src/pages/Users.tsx`, `server.py`, `src/i18n.py`. **Scope:** M

### Task 23: Who fixed a reading ✅
**Description:** `corrected_by` column (additive), saved by `save_fix`, shown in the truck
detail and as an Excel column; also written to `logs/corrections.jsonl`.

**Acceptance criteria:**
- [x] Old rows show nothing; new fixes show the user's name
**Verification:** tests. **Dependencies:** Task 21. **Files:** `src/store.py`, `src/config.py`, `web/src/components/TruckDetail.tsx`. **Scope:** S

---

## Phase 6: License with edition, users, lanes

### Task 24: New license fields and limits ✅
**Description:** Keys may carry `edition`, `users`, `lanes`. Missing = old key: users 5, lanes
as today. Trial: 5 users, 2 lanes. Adding a user or a lane over the limit is refused with a
plain message; existing users and lanes are never removed by a smaller key.

**Acceptance criteria:**
- [x] Old keys from Task 12 still read and work
- [x] Limits enforced in the API, not only the page

**Verification:** tests (test-driven). **Dependencies:** Tasks 12, 22. **Files:** `src/license.py`, `server.py`, `tests/test_license.py`. **Scope:** S

### Task 25: License tool options, usage on the License card
**Description:** `license_tool.py --edition --users --lanes` (Control Center repo); the License card shows
edition, "Users 7 of 10", "Lanes 2 of 2".

**Acceptance criteria:**
- [x] A key for 10 users, typed in, raises the limit with no restart
**Verification:** manual + tests. **Dependencies:** Task 24. **Files:** `web/src/pages/License.tsx`; Control Center repo: `license_tool.py`. **Scope:** S

### Checkpoint: User packs can be sold
- [ ] Tests pass; code review; a site upgraded from a real old setup keeps working

---

## Phase 7: Ship the Site edition

### Task 33: Site installer
**Description:** One `setup.exe` (Inno Setup): app, Python 3.12, models, built web app,
autostart, Windows firewall rule for port 8000 so other PCs on the site network can open it.
Signed with our code-signing certificate, so Windows trusts it.

**Acceptance criteria:**
- [ ] Fresh Windows PC with no Python: install, open from a phone on the same Wi-Fi
- [ ] Windows shows our name as publisher, no "unknown publisher" warning; the certificate's key
      stays outside the repo
- [ ] A Site installer has no `src/enterprise/`; an Enterprise installer has it (the web bundle's
      Enterprise pages stay hidden and do nothing without it)
**Verification:** install on a clean machine or VM. **Dependencies:** a code-signing certificate
(yours, ~SAR 1,500/year). **Files:** `installer/`. **Scope:** M

### Task 35: Customer docs
**Description:** Install checklist for the customer's IT, user guide for gate staff (en/ar),
support contacts and response times.
**Acceptance criteria:**
- [ ] A site's IT can prepare PC, cameras and network from the checklist alone
**Dependencies:** Tasks 33. **Files:** `docs/`. **Scope:** S

### Task 19: README for sites, renewal guide for you
**Description:** README: lanes and camera roles, ANPR setup, what customers see before and
after the license end date. A private guide for you: making keys, renewing, moving a site to
a new computer, backing up the private key.

**Acceptance criteria:**
- [ ] A new site can be set up with lanes and activated from the README alone
**Verification:** walk through on a fresh copy.
**Dependencies:** Tasks 10, 14, 25, 33 (the remote-renewal steps are added with Task 17).
**Files:** `README.md`, `license_server/README.md`. **Scope:** S

### Checkpoint: Site edition can be sold
- [ ] A fresh PC: install, activate with a real key, set up a lane, log trucks, using only the
      README and customer docs

---

## Phase 8: Control Center (your dashboard for every client)

A separate app that only you use, in its own private Control Center repo (`gate-reader-control`), hosted once for all clients: clients, contracts, licenses,
renewal keys, the health of every deployed site and which version it runs. It replaces the
plain license server. Design and check-in contract: plan.md, "Control Center".

### Task 15: Control Center server ✅
**Description:** In the Control Center repo (its own small FastAPI app and SQLite, never shipped to customers):
clients, sites, deployments (machine code, edition, version), contracts (start, end), licenses
(every key issued, the ledger) and heartbeats (kept 90 days). `POST /v1/checkin` takes the
contract in plan.md and answers active / ended plus a newer key when you renewed. Admin login
with password + authenticator code (TOTP). Signs keys with the same code as
`license_tool.py` (Task 12, same repo); the private key is a secret file on the server, never in the repo.

**Acceptance criteria:**
- [x] Renew: the next check-in returns the new key; End: the next check-in returns ended
- [x] Wrong password or code refused and slowed down; check-ins rate-limited; a check-in can
      only report for its own license and machine
- [x] A test fails if a private key file is ever inside the repo

**Verification:** tests (test-driven) with FastAPI's test client.
**Dependencies:** Task 12. **Files:** Control Center repo: `app.py`, `store.py`, `tests/`. **Scope:** M

### Task 16: App heartbeat and renewals
**Description:** The web app (`server.py`, which keeps running even when detection is stopped)
sends a heartbeat every 15 minutes when online: version, license state, detection running,
cameras online, last truck time, trucks and Check rows today, disk free, errors in the last 24 h
(from `logs/live/status.json` and the database). It saves a newer key and applies "ended".
5 s timeout, never blocks or slows the gate; no plates, container numbers or photos are sent.
The License card shows the last check-in and a *Check now* button.

**Acceptance criteria:**
- [ ] No internet / Control Center down / a 403 "unknown license" answer (a key issued offline
      with `license_tool.py`): nothing changes, no errors on screen
- [ ] Renewed in the Control Center: the site shows the new end date within 15 minutes (or at once with *Check now*)

**Verification:** tests against a local Control Center; manual.
**Dependencies:** Tasks 14, 15. **Files:** `src/checkin.py`, `src/license.py`, `server.py`, `web/src/pages/License.tsx`, `src/i18n.py`. **Scope:** M

### Task 40: Control Center app (pages) ✅
**Description:** `web/` in the Control Center repo (its own small React app, English only: it is your tool, not the
customer's). Pages: **Clients** (sites, edition, users and lanes bought, contract end);
**Client** (each site's deployments, licenses issued, health over time, notes); **Renewals**
(contracts ending in 60 / 30 days, *Issue renewal key*: new end date, users, lanes; delivered at
the next check-in, also copyable for sites with no internet); **Health** (every deployment green /
amber / red: silent, cameras down, disk low, license ending); **Versions** (who runs what, latest release).

**Acceptance criteria:**
- [x] A renewal is done in one place: pick the client, set the new end date, the site picks it up
- [x] A site silent for over 2 hours shows red with when it was last seen

**Verification:** browser check against a local Control Center with 3 fake deployments sending heartbeats.
**Dependencies:** Task 15. **Files:** Control Center repo: `web/`, `app.py`. **Scope:** L

### Task 41: Alerts to you ✅
**Description:** Email (SMTP) when: a deployment is silent > 2 h, a camera is offline > 1 h, disk
< 10 %, a license ends in 30 / 7 days, errors jump. One daily summary. Each alert once, then a
reminder a day later, not every 15 minutes. WhatsApp later if email isn't enough.

**Acceptance criteria:**
- [x] Each rule tested with fake heartbeats; no repeat alert within a day
**Verification:** tests; one real email to you. **Dependencies:** Task 15. **Files:** Control Center repo: `alerts.py`, `tests/`. **Scope:** S

### Task 42: Versions and releases
**Description:** One version number for the app (`VERSION`, e.g. 1.4.0) shown in the app, sent
in the heartbeat and in the installer's name; `CHANGELOG.md` in plain words. The Control Center
holds the latest version and marks older deployments. Updates are installed by you (remote
session + new installer); no automatic updates in v1.

**Acceptance criteria:**
- [x] The Versions page shows which clients are behind and since when
**Verification:** tests; manual. **Dependencies:** Task 40. **Files:** `VERSION`, `CHANGELOG.md`; Control Center repo: Versions page. **Scope:** S
**Status:** Control Center side done (releases list, behind since). Still open: `VERSION` and `CHANGELOG.md` in this repo; showing the version in the app and the heartbeat come with Task 16.

### Task 17: Put the Control Center online
**Description:** One small VPS in a Saudi data centre: Docker Compose (Caddy for HTTPS + the
app), private key, admin password and SMTP as secret files, nightly database backup to separate
storage, an offline backup of the private key. The admin pages may also be limited to your IP;
the check-in address stays open (rate-limited).

**Acceptance criteria:**
- [ ] HTTPS only; secrets not in the repo or logs; restore from backup tested once
- [ ] A test site picks up a renewal made in the online Control Center

**Verification:** the Control Center repo's `README.md` steps followed exactly on a fresh VPS.
**Dependencies:** Tasks 16, 40, your VPS. **Files:** Control Center repo: `README.md`, `deploy/`. **Scope:** M

### Task 18: Security review of licensing and the Control Center
**Description:** security-auditor agent reviews `src/license.py`, `src/checkin.py`, the
Control Center repo and the app's license endpoints; fix every confirmed finding.

**Acceptance criteria:**
- [ ] No high or medium findings left open
**Verification:** review report; tests for each fix.
**Dependencies:** Task 17. **Scope:** S

### Checkpoint: Control Center works
- [ ] Renew and end a test license from the online Control Center; health of 2 test sites shown;
      sites unaffected while the Control Center is down

---

## Phase 9: Manager dashboards (both editions) and Enterprise central HQ

**Both editions** (core code):

### Task 26: `updated_at`, sync cursor and the Enterprise hooks
**Description:** `updated_at` on every insert, merge and fix (additive column, old rows filled
from date + time). `meta.sync_cursor` remembers what HQ has. `Store.changed_since(cursor, n)`.
Also the one-time Enterprise hooks, so Enterprise tasks never edit core files: `server.py` loads
`src/enterprise/` (`register(app, store)`) when the folder is there and the license says
Enterprise; `src/i18n.py` adds `src/enterprise/i18n.py`'s texts; `web/src/App.tsx` shows the
pages in `web/src/enterprise/` for Enterprise licenses only.

**Acceptance criteria:**
- [ ] A fix moves the row past the cursor again; old databases upgrade, every row kept
- [ ] Without `src/enterprise/` the app starts and every test passes; with it and a Site key, no
      Enterprise route answers

**Verification:** tests (test-driven). **Dependencies:** None. **Files:** `src/store.py`, `server.py`,
`src/i18n.py`, `web/src/App.tsx`, `tests/test_store.py`, `tests/test_server.py`. **Scope:** M

### Task 43: Site manager role
**Description:** One more role between Operator and Admin, in both editions: **Site manager**
(everything at their site except cameras, settings and license; manages their site's users; sees
the Site dashboard). The HQ manager role is Enterprise (Task 31). Every API route keeps a lowest
role (Task 21's route test).

**Acceptance criteria:**
- [ ] A site manager can't open cameras, settings or license, nor another site's data
- [ ] Existing users keep their roles after the upgrade

**Verification:** tests (test-driven). **Dependencies:** Task 21. **Files:** `server.py`, `src/store.py`, `web/src/pages/Users.tsx`, `src/i18n.py`. **Scope:** S

### Task 45: Turnaround time (time in the yard)
**Description:** Pair each IN row with the next OUT row of the same container (or plate when
there's no container): time in the yard, trucks still inside, longest stays. A pure function
over rows (`src/turnaround.py`), used by both dashboards.

**Acceptance criteria:**
- [ ] Tested cases: normal in/out, out without in, in twice, a fixed reading that changes the pair
**Verification:** tests (test-driven). **Dependencies:** Task 6 (lanes have a direction). **Files:** `src/turnaround.py`, `tests/test_turnaround.py`. **Scope:** S

### Task 44: Site manager dashboard
**Description:** A Dashboard page for one site (also offered in the Site edition): today / this
week / this month: trucks in and out, trucks per hour, per lane, % verified, Check rows waiting
(link to them), cameras now and downtime today, fixes per staff member, busiest hours, and the
same period last week for comparison. Plain words, an (i) on every number.

**Acceptance criteria:**
- [ ] Numbers match the Records page for the same day (tested on a sample database)
- [ ] English and Arabic, phone width

**Verification:** API tests for the numbers; browser check en/ar. Use the dataviz skill for the charts.
**Dependencies:** Tasks 9, 43. **Files:** `web/src/pages/Dashboard.tsx`, `server.py`, `src/store.py`, `src/i18n.py`. **Scope:** M

**Enterprise only** (code in `src/enterprise/` and `web/src/enterprise/`, left out of Site installers):

### Task 27: HQ receive API
**Description:** In central mode (`server.py --central`): admin creates a site and gets a
one-time token (stored hashed). `POST /api/hq/rows` (batch upsert by site + row id),
`PUT /api/hq/photos/{path}`, `POST /api/hq/heartbeat`. Token checked on every call.

**Acceptance criteria:**
- [ ] Re-sending the same batch adds nothing; a changed row updates
- [ ] Wrong or revoked token refused; one site can't write another site's rows
- [ ] Size limits on batches and photos

**Verification:** tests (test-driven) with FastAPI's test client.
**Dependencies:** Task 26. **Files:** `src/enterprise/hq_api.py`, `src/enterprise/hq_store.py`, `tests/test_hq.py`. **Scope:** M

### Task 28: Site sync worker
**Description:** A thread in the site app: every 30 s sends up to 200 changed rows, then
their photos shrunk to ~1280 px, then a heartbeat each minute. Backs off when HQ is
unreachable; never blocks detection; resumes from the cursor after a restart.

**Acceptance criteria:**
- [ ] HQ down for an hour: no errors on screen, catches up afterwards, no duplicates
- [ ] Shows last successful sync time

**Verification:** tests against a local HQ (test-driven); manual with the network cable out.
**Dependencies:** Task 27. **Files:** `src/enterprise/sync.py`, `tests/test_sync.py` (started by the
Enterprise hook from Task 26, so this task can run beside app work). **Scope:** M

### Task 29: HQ mode in the app
**Description:** Central mode hides cameras/setup pages and adds a **Sites** page (online,
last sync, trucks today, cameras down, license state) and a site filter in Records and day
stats; Excel per site or for all sites.

**Acceptance criteria:**
- [ ] A site offline > 15 minutes shows as offline
- [ ] Excel for all sites has a Site column

**Verification:** browser check en/ar with 2 test sites (rows sent through Task 27's API).
**Dependencies:** Task 27. **Files:** `web/src/enterprise/Sites.tsx`, `web/src/pages/Records.tsx` (site
filter, shown only in HQ mode), `src/enterprise/hq_api.py`, `src/enterprise/i18n.py`. **Scope:** L

### Task 30: Site Settings: Connect to HQ
**Description:** Paste the HQ address and token; test the connection; show last sync and
anything waiting to be sent. Disconnect stops sending.

**Acceptance criteria:**
- [ ] A wrong token shows a plain message, not an error code
**Verification:** browser check en/ar. **Dependencies:** Task 28. **Files:** `web/src/enterprise/ConnectHq.tsx`, `src/enterprise/sync.py`, `src/enterprise/i18n.py`. **Scope:** S

### Task 31: HQ manager role and site-scoped HQ users
**Description:** The **HQ manager** role: the HQ dashboard and every site in their scope, read and
Excel, no camera settings. An HQ user is either all sites or a list of sites; every HQ query filters by it.

**Acceptance criteria:**
- [ ] A site-scoped user can't see another site's rows or photos, even by guessing URLs
**Verification:** tests (test-driven). **Dependencies:** Tasks 21, 29. **Files:** `src/enterprise/scope.py`, `server.py` (role check), `tests/test_hq.py`. **Scope:** S

### Task 46: HQ manager dashboard
**Description:** All sites in the HQ manager's scope in one view: trucks today and this week per
site, % verified, Check rows waiting, sites offline and cameras down, turnaround per site, a trend
chart and the sites that need attention first. A click on a site opens its Site dashboard
(read-only). Works in HQ mode (this phase) and on the customer's server (Task 38).

**Acceptance criteria:**
- [ ] A scoped HQ manager sees only their sites, even by guessing URLs
- [ ] Per-site numbers match each site's own dashboard

**Verification:** API tests with 2 test sites; browser check en/ar.
**Dependencies:** Tasks 29, 31, 43, 44, 45. **Files:** `web/src/enterprise/HqDashboard.tsx`, `src/enterprise/hq_api.py`, `src/enterprise/i18n.py`. **Scope:** M

### Task 32: Deploy HQ to a VPS
**Description:** A KSA-region VPS: Caddy (HTTPS), the app as a service, nightly
`sqlite3 .backup` + photos to separate storage, uptime monitor. `docs/hq-runbook.md`:
new customer, restore from backup, update.

**Acceptance criteria:**
- [ ] HTTPS only; secrets not in the repo
- [ ] Restore from last night's backup tested once

**Verification:** follow the runbook from scratch on a fresh VPS.
**Dependencies:** Tasks 29-31, 46. **Files:** `docs/hq-runbook.md`, `deploy/hq/`. **Scope:** M

### Checkpoint: Enterprise works
- [ ] Two sites sync to a test HQ, an hour offline, catch up, no duplicates
- [ ] security-auditor review of the HQ API and sync

---

## Phase 10: Enterprise on the customer's server (when a customer chooses it)

### Task 37: Enterprise on the customer's server: design and sizing test
**Description:** Option 2 in the pricing guide: one central install on the customer's server reads
every site's cameras through each site's NVR over the company network; staff at each site open
the same app and see only their own site. Decide how a site is stored (a `site` on lanes and rows,
shared with Phase 9), how many lanes one machine reads (CPU cores vs NVIDIA GPU), and what a site's
link going down looks like (that site pauses, Live shows it offline).

**Acceptance criteria:**
- [ ] Design written in plan.md, reusing Phase 9's site column and site-scoped users (Task 31)
- [ ] `bench.py` with 8 lanes on the target hardware (or a VM that size): the guide's sizing
      (32 cores or one GPU, 64 GB, 2-4 Mbit/s per camera) confirmed or corrected

**Verification:** numbers recorded in plan.md; the pricing guide updated if they differ.
**Dependencies:** Tasks 6, 29, 31; a customer choosing Option 2. **Files:** `tasks/plan.md`, `bench.py`. **Scope:** M

### Task 38: Enterprise on the customer's server: build
**Description:** Central mode that reads cameras: cameras and lanes carry a site; Live, Records,
day stats and Excel filter by the user's sites; the Sites page shows each site's cameras online or
offline; the Site and HQ dashboards (Tasks 44-46) work the same. The license carries the
central edition and its lane count.

**Acceptance criteria:**
- [ ] Two test sites (fake recorders) on one install: each site's user sees only its own trucks
      and photos, even by guessing URLs
- [ ] One site's recorder offline pauses only that site

**Verification:** tests (test-driven) for site scoping; browser check en/ar; build and commit `web/dist`.
**Dependencies:** Task 37. **Files:** `src/enterprise/`, `web/src/enterprise/`, `cctv.py`, `src/lanes.py`, `src/license.py`. **Scope:** L

### Checkpoint: Enterprise on a customer's server works
- [ ] Two test sites on one install, each sees only its own; security-auditor review of site scoping

---

## Phase 11: Extras

### Task 39: Import old gate logs from Excel
**Description:** A tool for the paid "Import old Excel logs" service: read a customer's old gate
log (their columns mapped once: date, time, container, plate, direction), check each container
number with the check digit, and add the rows to `logs/gate.db` marked as imported (no photos).
Excel files are then rebuilt from the database as usual.

**Acceptance criteria:**
- [ ] Re-running the same file adds nothing; rows that can't be read are listed in a report, never dropped silently
- [ ] Imported rows are marked as such in Records and Excel

**Verification:** tests with a small sample workbook.
**Dependencies:** None (easier after Task 26). **Files:** `tools/import_excel.py`, `src/store.py`, `tests/test_import.py`. **Scope:** M

### Task 34: Optional: compiled app
**Description:** Nuitka build so the license check isn't plain Python source.
**Acceptance criteria:**
- [ ] Same tests pass against the compiled build
**Dependencies:** Task 33. **Scope:** M

---

### Checkpoint: Complete
- [ ] All acceptance criteria met, tests and build pass
- [ ] Reviewed by you
