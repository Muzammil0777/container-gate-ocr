# Implementation Plan: Gate lanes (multi-camera + ANPR) and licensing

Tasks with acceptance criteria and checks: [todo.md](todo.md).
Previous plan (React app, done): [archive/plan-react-app.md](archive/plan-react-app.md).

## Overview
1. **Gate lanes.** Each gate lane (Entry, Exit) gets up to three cameras: two that read the
   container from different angles and one ANPR camera for the plate. All cameras of a lane
   feed **one** truck reading, so each truck becomes **one row** with container, plate and
   photos from every camera, and a container read the same way by both cameras is marked
   **verified**.
2. **Licensing.** The app is activated with a signed license key that runs out (e.g. after
   a year). From 30 days before, staff see "contact us to renew". Renewal is a new key, typed
   in or fetched automatically from your **Control Center** (added 2026-10-28): your own
   dashboard for every client's contract, license keys, site health and app version.
3. **Editions and users (added 2026-10-20).** Two editions are sold as a yearly subscription:
   **Site** (one site, opened from the site network) and **Enterprise** (several sites + one
   central HQ for the manager). Users are sold in packs of 5, so the app needs named logins
   and seat limits. Prices: `Gate_Reader_Pricing.xlsx` (not committed).
4. **Manager dashboards (added 2026-10-28).** A Site manager dashboard (one site) and an HQ
   manager dashboard (all sites), with two new roles.

## What the code does today (why this needs a design, not a tweak)
- Each camera runs its own `GateTracker` and logs its own rows (`cctv.py: watch`).
- Two rows become one only in `Store.add`: **same direction and same plate or same
  container serial** within 5 minutes.
- A plate-only camera (ANPR) and a container-only camera share neither, so today they would
  give **two rows per truck**. Two container cameras merge only when both read the serial
  exactly the same, and nothing records that a second camera agreed.

## Architecture Decisions

### Lanes
- **A lane = cameras that see the same truck.** `cameras.json` keeps its flat camera list; a
  camera gets `lane` and `role` (`container`, `plate` or `both`). Lane settings (direction,
  location) live in `lanes`. A camera without a lane is a lane of its own with role `both`,
  so **every existing site keeps working unchanged**.
- **Both container cameras read; agreement is the check.** Instead of "camera 1 reads,
  camera 2 confirms", both cameras' reads vote together (more reads, more chances to get every
  digit), and the row records **how many cameras agreed** on the final number. Whichever
  camera happens to have the better view of a truck wins, so neither camera is a single point
  of failure.
- **Pairing by time, per lane.** A truck visit at a lane opens with the first read from any
  of its cameras and closes when the lane goes quiet (`gap_s`) or after `pair_window_s`
  (default 30 s: the plate camera sees the front, the container cameras the rear). A new,
  different plate while the visit already has a confirmed plate starts a new visit (next truck).
- **One row per truck, always written (decided).** A truck is never dropped because the second
  camera missed it. The row is written and marked: *Verified by 2 cameras* / *1 camera only*.
  Rows that are not verified show **Check** in Records, like today.
- **ANPR: two ways in.** (a) Any camera with role `plate` is read by our own Saudi plate
  reader (works with any camera, costs CPU). (b) A Hikvision ANPR camera's own plate results
  are received from the camera (ISAPI event stream: plate text + plate photo), which costs no
  CPU and is usually better at night. (b) is built only after a test with the real camera
  model (Task 2).
- **Database grows additively.** New columns are added to existing databases on start
  (`ALTER TABLE ADD COLUMN`); old rows stay valid. Excel gets a *Verified* column. The
  database stays the master record.

### Licensing
- **Signed keys, checked offline.** A license is a small signed text (Ed25519): customer,
  site, machine code, start, end, number of cameras. The app holds only the **public** key;
  the **private** key stays with you, so nobody can make a key without you. Works with no
  internet. Needs one new library: `cryptography` (Python's standard library has no
  public-key signatures; a shared secret in the app would let anyone make keys).
- **Bound to one computer.** The app shows a machine code (from Windows' machine ID); the key
  is issued for that code. A new laptop needs a re-issued key.
- **Remote control is optional, never required.** When the site has internet, the app checks
  in with your Control Center (every 15 minutes, see below): it picks up renewals
  automatically, and you can end a license early. Without internet everything still works until the key's end date, and
  renewal is done by typing in a new key.
- **New installs: 14-day trial (decided).** Everything works for 14 days from first start,
  so setup and testing can happen before you issue the key for that computer.
- **What expiry does (decided).** 30 days before: a banner on every page with your contact
  details. After the end date: 14 days of grace with a red banner. Then detection stops.
  Records, photos, corrections and Excel downloads **keep working**: the customer's data is
  never locked away.
- **Honest limit.** The app is Python source on the customer's laptop; a determined developer
  could remove the check. Signed keys stop casual copying and sharing; real protection
  comes from compiling the app into an installer and from the sales contract (optional
  later phase).

### Named users and seats (Phase 5)
- Today each site has **one shared password** (`server.py`, `site_password`), so users can't
  be counted. A `users` table in `logs/gate.db`: username, display name, password hash (same
  PBKDF2 as now), role, active, created.
- **Roles:** *Admin* (settings, cameras, users), *Operator* (live, records, fixes), *Viewer*
  (records and Excel only).
- **A user = an active named login**, not people online at once: easy to count and explain.
- The session cookie carries the user id inside the existing HMAC, so disabling a user logs
  them out at once.
- **Upgrade:** on first start the old site password becomes user `admin`; nothing breaks.
- Fixes record who made them (`corrected_by` column and in `logs/corrections.jsonl`).
- Adding a user over the license limit shows "Your license allows N users. Contact us to add
  5 more." Disabling a user frees a seat.

### License carries edition, users, lanes (Phase 6)
- Key gets `edition` (`site` / `enterprise`), `users`, `lanes`. Old keys keep working:
  missing `users` = 5, missing `lanes` = cameras as today. Trial = 5 users, 2 lanes.
- **Adding 5 users = a new key**, typed in or picked up by the daily check-in (Tasks 15-16).
  No reinstall, no visit. The License card shows "Users 7 of 10, Lanes 2 of 2".

### Enterprise: central HQ (Phase 9)
```
 Site PC (Riyadh)  ─┐
 Site PC (Jeddah)  ─┤  HTTPS push, outbound only     ┌───────────────────────────┐
 Site PC (Jubail)  ─┼──────────────────────────────▶ │ Central HQ (KSA cloud VPS) │ ◀── Manager's browser
 Site PC (Dammam)  ─┘  (records, small photos,       │ all sites' records, health │     (anywhere)
                        heartbeat every minute)       └───────────────────────────┘
```
- **Each site keeps working on its own.** Detection, records and Excel stay on the site PC.
  Internet down: nothing stops; the site catches up when it is back.
- **Sites push, HQ never connects in.** Outbound HTTPS only: no VPN, no open ports, works on
  4G. Each site has its own token, made at HQ and pasted once into the site's Settings
  ("Connect to HQ"); HQ stores it hashed.
- **What is sent:** new and changed rows (an `updated_at` column, so fixes sync too), photos
  shrunk to ~1280 px (full size stays on site), and a heartbeat each minute (service
  running, cameras online, license state, disk free).
- **No duplicates:** HQ keys each row by (site, site's row id), so re-sending is harmless.
- **HQ = same code in central mode** (`server.py --central`): same `Store` with a `site`
  column, same React app with a site filter, a **Sites page** (online/offline, last sync,
  trucks today, cameras down) and Excel per site or across sites.
- **Who sees what:** Phase 5 users plus a site scope: an HQ manager sees all sites, a site
  supervisor only theirs. HQ users count toward the company's user packs.
- **Hosting:** one small VPS **per customer** (data kept apart, simple to price) in a
  Riyadh/Jeddah data centre (PDPL: data stays in KSA). Caddy for HTTPS, runs as a service,
  nightly database backup to separate storage, uptime monitor. HQ keeps photos 90 days
  (setting), rows forever.
- **Not in v1 (add when a customer asks):** changing site settings from HQ (remote desktop
  for now), email/WhatsApp alerts, Postgres (SQLite is fine below ~20 sites).

### Added 2026-10-28 (from the pricing guide and the yard footage)
- **Enterprise on the customer's server (Phase 10).** The pricing guide sells a second
  Enterprise option: one central install on the customer's own server reads every site's
  cameras through each site's NVR over their company network (central fee SAR 7,000; not yet
  in `Gate_Reader_Pricing.xlsx`). No site PCs, no sync: it reuses Phase 9's site column and
  site-scoped users. A site's link going down pauses that site's reading. Sizing in the guide
  (8 lanes: ~32 cores or one NVIDIA GPU, 64 GB, 2-4 Mbit/s per camera) is an estimate until
  Task 37 measures it. Built only when a customer chooses this option.
- **Import old Excel logs (Task 39).** Sold as a one-time service. Imported rows go into
  `logs/gate.db` (the master record) marked as imported; Excel is rebuilt from it as always.
- **Accuracy (Task 36).** The yard recording read the container 22/22 but also produced junk
  codes from door markings, and white-container markings could still pass as plates.
- **Installer signing (Task 33).** A code-signing certificate so Windows trusts `setup.exe`.

### Editions and repos (decided 2026-10-31)
- **One repo and one app for both editions.** About 85-90 % of the code (OCR, lanes, Records,
  Excel, users, licensing, Site dashboard) is the same in both; two repos or long-lived edition
  branches would mean every fix twice and growing drift. The license key's `edition` decides what
  is switched on.
- **Enterprise-only code lives in its own folders:** `src/enterprise/` (HQ API, sync, site scope)
  and `web/src/enterprise/` (Sites page, HQ dashboard, Connect to HQ). Core code never imports
  them directly: three hooks added once in Task 26 (`server.py` loads `src/enterprise/` when it is
  there and the key says Enterprise, `src/i18n.py` adds its texts, `web/src/App.tsx` shows its
  pages). A **Site installer leaves `src/enterprise/` out**, so Site customers don't get the
  server-side Enterprise code; the web bundle's Enterprise pages stay hidden and do nothing without it.
- **The folders also split the parallel work:** a session on Enterprise works in its folders
  while the other works on the core, without touching the same files.
- **The Control Center is its own private repo, `gate-reader-control`** (created in Task 12): a
  different product, only for you, deployed on your own server and never in a customer installer.
  The license tool (`license_tool.py`, which signs keys) lives there too, so customers only ever
  get the code that *checks* keys. The key format is shared through a sample key in this repo's
  `tests/fixtures/license/`, tested by both repos.

### Control Center: your dashboard for every client (Phase 8, added 2026-10-28)
```
 Site PC (client A) ─┐  heartbeat every 15 min, HTTPS, outbound   ┌──────────────────────┐
 Site PC (client B) ─┼──────────────────────────────────────────▶ │ Control Center (you) │ ◀── your browser
 HQ server (client C)┘  ◀── newer key / "ended" in the answer      │ one KSA VPS, all     │     (password + 2FA)
                                                                  │ clients              │ ──▶ email alerts
                                                                  └──────────────────────┘
```
- **Separate app, separate private repo** (`gate-reader-control`: own FastAPI + SQLite + small
  React app), never in a customer's installer. English only: it is your tool, not the gate staff's.
- **What it holds:** clients, sites, contracts (start, end), every license key issued (the
  ledger), deployments (machine code, edition, version) and their heartbeats (90 days).
- **Renewal in one place:** pick the client, set the new end date (and users / lanes), the
  Control Center signs the key, and the site picks it up at its next check-in. Sites with no
  internet: copy the key and type it in, as before. `license_tool.py` (same repo) stays for offline use.
- **Health:** each deployment is green / amber / red (silent > 2 h, camera down > 1 h, disk
  < 10 %, license ending, errors); alerts by email, one daily summary.
- **Versions:** each deployment reports its version; you see who is behind. Updates are
  installed by you (remote session + installer); no automatic updates in v1.
- **The private key lives on the Control Center server** (a secret file, plus an offline
  backup), so renewals are one click. The price: if that server were broken into, someone could
  make keys. Hence: password + authenticator code, admin pages limited to your IP if possible,
  security review (Task 18), and key rotation by key id if it ever leaks.
- **The heartbeat contract** (both sides build to this, so Tasks 15 and 16 can run in parallel):
  `POST /v1/checkin` with `{license_id, machine, version, edition, state, health: {detection_running,
  cameras_total, cameras_online, last_truck_at, trucks_today, check_rows_today, disk_free_gb,
  errors_24h}}`; answer `{status: "active" | "ended", key?: "<newer key>"}`. No plates, container
  numbers or photos are ever sent. Sent by `server.py` (always running, even when detection has stopped).

### Manager dashboards and roles (Phase 9, added 2026-10-28)
- **Roles:** Viewer (records, Excel) < Operator (gate staff: + live, fixes) < Site manager (+ Site
  dashboard, their site's users) < Admin (+ cameras, settings, license): both editions.
  **HQ manager** (Enterprise only): the HQ dashboard and every site in their scope, read-only plus Excel.
- **Site dashboard** (also in the Site edition: it helps sell): trucks in/out per hour and lane,
  % verified, Check rows waiting, camera downtime, fixes per staff member, turnaround time.
- **HQ dashboard:** every site side by side, which sites need attention first, trends; a click
  opens a site's dashboard. The same pages work on our hosted HQ and on the customer's server.
- **Turnaround time** (IN to OUT of the same container or plate) is new logic, kept as a pure
  function so both dashboards share it.

### Hosting: where each part runs (added 2026-10-28)
| Part | Runs on | How | Who looks after it |
|---|---|---|---|
| Site edition, Enterprise option 1 sites | The customer's Windows PC at the gate | Installer (Task 33): app + detection as Windows services that start with the PC; staff open `http://<PC address>:8000` on the site network; firewall rule for port 8000; fixed address for the PC on their router | You, by remote session (AnyDesk) |
| Enterprise option 1: HQ | One VPS per customer in a Saudi data centre | Docker Compose: Caddy (HTTPS, automatic certificate) + `server.py --central`; nightly backups; customer's own address such as `hq.<customer>.com` or one under your domain | You (in the HQ fee) |
| Enterprise option 2: central install | The customer's server or VM in their data centre (Windows Server, or Linux) | Same app, central mode, reading each site's NVR over their network; opened on their intranet with their HTTPS certificate; needs CPU/GPU sized in Task 37 | Their IT, with your remote support over their VPN |
| Control Center | One small VPS of yours (Saudi data centre) | Docker Compose: Caddy + the `gate-reader-control` app; secrets as files; nightly backups | You |
- Site PCs don't use Docker: a plain installer is lighter and easier for site IT, and OCR needs
  the CPU. HQ and Control Center do: the same Compose file per customer makes each new HQ a
  copy-and-fill-in job.
- A site needs internet only for Control Center check-ins (and HQ sync in Enterprise). Option 2
  customers often block outbound traffic: ask them to allow the Control Center's address, or
  renew by typing in keys.
- Licenses are bound to a machine code. A cloned VM can share Windows' machine ID, so option 2
  installs get their key after the VM is final.

### How we build it (skills)
- **Test-driven** for the lane tracker and the license checks (pure logic, many edge
  cases): tests first, from real failure cases.
- **Security review** (security-auditor agent) of the license code and server before release.
- **Code review** (code-reviewer agent) at every checkpoint; **browser checks** for every UI
  task in English and Arabic; one task = one commit, tests passing before each commit.

## Task List
Phases are in build order (reordered 2026-10-28): first what the BAFCO deck already shows
(lanes, verified rows), then what must exist before selling (users, license limits, installer).
Task numbers stay as first planned.

### Phase 0: Evidence first (fail fast)
- [x] Task 1: Multi-camera speed test on this laptop
- [ ] Task 2: ANPR camera test (real camera)

### Checkpoint: Decide hardware and ANPR mode with you

### Phase 1: Lane foundation
- [x] Task 3: Database: verification and lane columns (old databases upgrade)
- [x] Task 4: Settings: lanes and camera roles (old settings keep working)
- [x] Task 5: Lane tracker: one truck from several cameras (test-driven)

### Checkpoint: Lane logic

### Phase 2: Detection service
- [x] Task 6: Service runs cameras by lane, one row per truck with every camera's photo (real-recording check open)
- [ ] Task 7: Hikvision ANPR events as the plate source (if Task 2 succeeds)
- [ ] Task 36: Accuracy on real yard footage: junk container codes, white-container markings, night (yard parts done; night open)

### Checkpoint: End to end with real recordings

### Phase 3: App
- [x] Task 8: Cameras page: lanes and what each camera reads; Live grouped by lane
- [x] Task 9: Records and Excel: "Verified by 2 cameras", every camera's photo
- [ ] Task 10: Setup wizard: second container camera and plate camera

### Checkpoint: Lanes complete

### Phase 4: License in the app
- [x] Task 11: License check: signed key, machine code, states, clock guard (test-driven)
- [ ] Task 12: Your license tool: make keys, issue and inspect licenses (creates the Control Center repo)
- [ ] Task 13: Activation screen, License card, expiry banners
- [ ] Task 14: After the grace period: detection stops, data stays available

### Checkpoint: Licensing works offline

### Phase 5: Named users and seats
- [ ] Task 20: Users table, upgrade from the site password
- [ ] Task 21: Login by username, roles checked on every API route
- [ ] Task 22: Users page (admin)
- [ ] Task 23: Who fixed a reading (`corrected_by`)

### Phase 6: License with edition, users, lanes
- [ ] Task 24: New license fields, user and lane limits enforced
- [ ] Task 25: License tool options, usage on the License card

### Checkpoint: User packs can be sold

### Phase 7: Ship the Site edition
- [ ] Task 33: Site installer (setup.exe, signed, autostart, firewall rule for port 8000)
- [ ] Task 35: Customer docs (en/ar)
- [ ] Task 19: README for sites, renewal guide for you

### Checkpoint: Site edition can be sold

### Phase 8: Control Center (your dashboard for every client)
- [ ] Task 15: Control Center server: clients, contracts, licenses, check-in, 2FA login
- [ ] Task 16: App heartbeat every 15 minutes, picks up renewals
- [ ] Task 40: Control Center pages: Clients, Renewals, Health, Versions
- [ ] Task 41: Alerts to you by email
- [ ] Task 42: Versions and releases (`VERSION`, `CHANGELOG.md`)
- [ ] Task 17: Put the Control Center online (HTTPS) and renew a site remotely
- [ ] Task 18: Security review of licensing and the Control Center, fix findings

### Checkpoint: Remote renewal works

### Phase 9: Manager dashboards (both editions) and Enterprise central HQ
Both editions (core code):
- [ ] Task 26: `updated_at`, sync cursor and the Enterprise hooks
- [ ] Task 43: Site manager role
- [ ] Task 45: Turnaround time (time in the yard)
- [ ] Task 44: Site manager dashboard

Enterprise only (`src/enterprise/`, `web/src/enterprise/`):
- [ ] Task 27: HQ receive API: enrol site, rows, photos, heartbeat
- [ ] Task 28: Site sync worker: push, retry, resume after offline
- [ ] Task 29: HQ mode in the app: site filter, Sites page, cross-site Excel
- [ ] Task 30: Site Settings: Connect to HQ
- [ ] Task 31: HQ manager role and site-scoped HQ users
- [ ] Task 46: HQ manager dashboard
- [ ] Task 32: Deploy HQ to a VPS, with a runbook

### Checkpoint: Two sites sync to a test HQ, survive an hour offline, no duplicates

### Phase 10: Enterprise on the customer's server (when a customer chooses it)
- [ ] Task 37: Design and sizing test (8 lanes on one server)
- [ ] Task 38: Central install reads every site's cameras, each site sees only its own

### Checkpoint: Two test sites on one install, each sees only its own

### Phase 11: Extras
- [ ] Task 39: Import old gate logs from Excel (paid service)
- [ ] Task 34: Optional: compiled app (Nuitka)

### Checkpoint: Complete
- [ ] All tests pass, build clean, reviewed by you

## Task 1 results: speed on this laptop (2026-10-19)
Ryzen 7 5800U (8 cores / 16 threads), CPU only. Synthetic 4K recording (30 s, two trucks),
`py -3.12 bench.py yard_4k.mp4 --copies N --fps 4`: every stream decodes all its frames in real
time and they share one OCR engine, like the live service.

| Cameras at once | Looks/s per camera | All together | Trucks found (of 2) |
|---|---|---|---|
| 1 | 0.79 | 0.79 | 2 |
| 2 | 0.37-0.40 | 0.77 | 1-2 |
| 3 | 0.23-0.27 | 0.77 | 1-2 |
| 4 | 0.17-0.20 | 0.73 | 0 |

- **The laptop reads ~0.77 pictures per second in total, whatever the number of cameras.**
  One 4K look takes ~1.3 s and looks run one at a time. A reading area (60 % of the picture)
  did not change this.
- This is the worst case: here every camera always has a truck. Live, a camera with no
  movement is skipped, so an idle lane costs almost nothing. With **one truck at a time**, its
  lane's 2 container cameras get ~0.4 looks/s each: the same total reads per truck as today,
  but from two angles. With trucks at both gates at once, ~0.2 each, which found nothing above.

**Recommendations**
1. **ANPR camera reads plates itself (Task 7, option b).** Plate OCR on our side would be a
   third stream per lane; on this laptop that is not affordable.
2. **2 container cameras per lane, 2 lanes, on this laptop: only if trucks rarely arrive at
   both gates at the same moment.** Otherwise a stronger PC (desktop 8-16 core CPU), or an
   NVIDIA GPU (`use_cuda`, already supported: typically several times faster).
3. **Worth trying before buying hardware:** run 2 OCR engines side by side with fewer CPU
   threads each (one 4K look may not use all 16 threads well). Small change, measured with
   this same command; done as part of Task 6 if it helps.
4. Re-run on **real recordings** from both angles (Open Question 2) before deciding: real
   yards have less text per frame than this test video.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| More cameras on one CPU laptop means fewer reads per camera (4K OCR is ~1 s/frame; 6 streams share it), so accuracy could **drop** | High | Task 1 measures it before anything is built. Levers: reading areas, ANPR doing plates on the camera (Task 7), lower looks/second for the 2nd angle, a stronger PC or the existing GPU option |
| Plate (front) and container (rear) of two close trucks paired wrongly | Med | Pair by lane + time window; a different plate opens a new visit; photos from every camera in the row, so a person can fix it in Records |
| Tuning without real footage from both angles | High | You provide recordings of real trucks from both container cameras and the ANPR camera (Open Question 2); tests replay them |
| Hikvision ANPR output differs by model/firmware (Saudi plates, Arabic letters) | Med | Task 2 captures real events into test files before Task 7 is written; option (a) works with any camera meanwhile |
| Private signing key leaked or lost | High | Kept outside the repo (git-ignored, checked by a test); one backup offline; key rotation supported by key id in each license |
| Customer sets the PC clock back to extend the license | Low | Clock guard: the app remembers the latest time it has seen; a clock far behind it counts as the latest time |
| License checks bypassed by editing Python source | Med | Deterrent only (stated above); optional later: compiled installer |
| A license problem stops a gate mid-shift | High | Warnings start 30 days ahead, 14 days grace, never stops records or exports, Control Center outages never affect the app |
| Control Center broken into: someone makes keys | Med | Password + authenticator code, admin pages limited to your IP, security review, key rotation by key id |
| Two parallel sessions change the same file | Med | Each round's two tasks touch different files (todo.md, "Parallel work"); `web/dist` is built only after merging |
| Upgrading to named users locks a site out | High | The old site password becomes user `admin` automatically; tested on a copy of a real `cameras.json` + `gate.db` |
| Site internet is slow or metered (4G) | Med | Photos shrunk before sending, batches, resume where it stopped; sync never blocks detection |
| HQ server down or lost | Med | Sites are unaffected (they keep everything); nightly backups; HQ can be rebuilt and sites re-send |

## Decisions (2026-10-19)
- Unverified trucks are written and marked **Check**, never held back or dropped.
- After expiry: 14 days grace, then detection stops; records and Excel stay available.
- New installs get a 14-day trial before a key is needed.
- The React-app plan is archived in `tasks/archive/`.

## Open Questions (still needed)
1. **ANPR camera:** which brand and model? Does it read Saudi plates (Arabic + Latin) itself?
   (needed for Task 2)
2. **Recordings:** 5-10 minutes of trucks from both container angles plus the ANPR camera,
   recorded at the same time, exported from the NVR (needed for Tasks 1 and 6)
3. **Hardware:** stay on the Ryzen 7 5800U laptop, or a stronger PC per site if Task 1 shows
   it's needed?
4. **License details:** one license per computer (recommended)? A limit on cameras per
   license? What contact details should the renewal banner show? (needed for Task 13)
5. **Control Center:** do sites have internet? Which Saudi VPS provider and domain for the
   Control Center? (needed for Task 17)
6. **Enterprise on the customer's server:** does a customer want it, and on what hardware?
   (needed for Task 37)
