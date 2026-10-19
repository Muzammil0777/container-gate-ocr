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
   in or fetched automatically from a small license server you control.

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
  in once a day with your license server: it picks up renewals automatically, and you can end
  a license early. Without internet everything still works until the key's end date, and
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

### How we build it (skills)
- **Test-driven** for the lane tracker and the license checks (pure logic, many edge
  cases): tests first, from real failure cases.
- **Security review** (security-auditor agent) of the license code and server before release.
- **Code review** (code-reviewer agent) at every checkpoint; **browser checks** for every UI
  task in English and Arabic; one task = one commit, tests passing before each commit.

## Task List

### Phase 0: Evidence first (fail fast)
- [ ] Task 1: Multi-camera speed test on this laptop
- [ ] Task 2: ANPR camera test (real camera)

### Checkpoint: Decide hardware and ANPR mode with you

### Phase 1: Lane foundation
- [ ] Task 3: Database: verification and lane columns (old databases upgrade)
- [ ] Task 4: Settings: lanes and camera roles (old settings keep working)
- [ ] Task 5: Lane tracker: one truck from several cameras (test-driven)

### Checkpoint: Lane logic

### Phase 2: Detection service
- [ ] Task 6: Service runs cameras by lane, one row per truck with every camera's photo
- [ ] Task 7: Hikvision ANPR events as the plate source (if Task 2 succeeds)

### Checkpoint: End to end with real recordings

### Phase 3: App
- [ ] Task 8: Cameras page: lanes and what each camera reads; Live grouped by lane
- [ ] Task 9: Records and Excel: "Verified by 2 cameras", every camera's photo
- [ ] Task 10: Setup wizard: second container camera and plate camera

### Checkpoint: Lanes complete

### Phase 4: License in the app
- [ ] Task 11: License check: signed key, machine code, states, clock guard (test-driven)
- [ ] Task 12: Your license tool: make keys, issue and inspect licenses
- [ ] Task 13: Activation screen, License card, expiry banners
- [ ] Task 14: After the grace period: detection stops, data stays available

### Checkpoint: Licensing works offline

### Phase 5: Remote license control
- [ ] Task 15: License server: daily check-in, renew and end licenses
- [ ] Task 16: App checks in daily and picks up renewals
- [ ] Task 17: Put the license server online (HTTPS) and renew a site remotely

### Checkpoint: Remote renewal works

### Phase 6: Release
- [ ] Task 18: Security review of licensing, fix findings
- [ ] Task 19: README for sites, renewal guide for you

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
| A license problem stops a gate mid-shift | High | Warnings start 30 days ahead, 14 days grace, never stops records or exports, license server outages never affect the app |

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
5. **Remote control:** do sites have internet? Where should the license server run (a small
   cloud server, ~$5/month, in your account)? (needed for Task 17)
