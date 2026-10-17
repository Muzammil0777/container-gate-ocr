# Implementation Plan: React app for Container Gate OCR

## Overview
Replace the Streamlit UI (`app.py`) with a React web app that looks polished, works in English
and Arabic (right-to-left), and can be used by gate staff with no technical knowledge. Opened
from any computer or phone on the site network. The detection service (`cctv.py`), the
database (`src/store.py`) and the OCR code stay exactly as they are. A small Python API sits
between them and the React app.

```
cameras ──► cctv.py (unchanged) ──► logs\gate.db, logs\live\*.jpg, status.json
                  ▲                              │
     cameras.json │                              ▼
                  └──────────── server.py (FastAPI: /api/* + the built React app) ◄── browser (any PC / phone)
```

## Architecture Decisions
- **One process, one port per site.** `server.py` (FastAPI + uvicorn) serves `/api/*` and the
  built React files. Site laptops need **no Node.js**: the built app (`web/dist`) ships with
  the repo/release, so installing on a new site is still "install Python, double-click".
- **The API wraps code that already exists.** It calls `Store`, `to_excel`, `to_zip`,
  `Recognizer`, `GateLog`, `hikvision_url`, `port_open`. Helpers that live inside `app.py`
  today (config load/save, service status/start, frame grab, correction validation) move to
  `src/config.py` so both UIs can use them during the switch-over.
- **React + Vite + TypeScript + Mantine.** Mantine provides good-looking components (tables,
  date picker, forms, notifications) and has built-in right-to-left support for Arabic, so
  we write very little CSS ourselves.
- **One source of truth for text.** React fetches the English/Arabic strings from
  `src/i18n.py` through `/api/text`. No second translation file.
- **Live view by polling, not WebSockets.** Fetch `/api/status` every 2 s and reload each
  camera image. Same as the Streamlit app does today, and enough for a few cameras.
- **Photos are served by record id** (`/api/records/{id}/snapshot`), never by file path, so
  the browser can't ask for arbitrary files on the laptop.
- **Video tests run as a background job** with a progress endpoint, so a long video doesn't
  freeze the page.
- **Streamlit stays until the React app does everything it does.** It is removed in the last task.

## Task List
Details, acceptance criteria and checks per task: [todo.md](todo.md).

### Phase 1: Foundation
- [x] Task 1: Move shared helpers out of app.py into src/config.py
- [x] Task 2: API server and React shell (one port, English/Arabic, navigation)

### Checkpoint: Foundation
- [ ] `python -m pytest` passes, `npm run build` passes, `start_gate.bat` still works (Streamlit)
- [ ] http://localhost:8000 shows the React shell; switching to Arabic flips the layout

### Phase 2: Daily use (what gate staff use every day)
- [x] Task 3: Live page
- [ ] Task 4: Records page: browse a day, see photos
- [ ] Task 5: Records page: fix a reading, downloads

### Checkpoint: Daily use
- [ ] A truck logged by cctv.py shows on Live within a few seconds
- [ ] A correction made in React shows in the Excel file and in the Streamlit app

### Phase 3: Setup and testing
- [ ] Task 6: Cameras page: NVR login, camera list
- [ ] Task 7: Add camera: draw the reading area on a picture, test the camera
- [ ] Task 8: Test page: photos and stream URL
- [ ] Task 9: Test page: video file as a background job

### Checkpoint: Feature parity
- [ ] Everything the Streamlit app does can be done in the React app

### Phase 4: Made for non-technical users, and roll-out
- [ ] Task 10: First-run setup wizard and plain-language help
- [ ] Task 11: Site login (one password per site)
- [ ] Task 12: Switch launchers to the new app, update README, remove Streamlit

### Checkpoint: Complete
- [ ] Fresh install on a clean Windows PC by following README only
- [ ] Human review before merge

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| onnxruntime DLL clash on Windows (already seen with pandas) also happens under uvicorn | High | Task 2 imports `src.recognizer` first, same as app.py, and checks it on this laptop before anything else is built |
| Built React files go stale vs. source | Med | `npm run build` in the release step; README says so; CI check optional later |
| Opening the app to the network exposes NVR password and settings to anyone on the LAN | High | Task 11 (login). Until then, server binds to localhost only by default |
| Excel/ZIP of a busy month is large or slow | Low | Built on request only (same as today) |
| Two UIs writing cameras.json during switch-over | Low | Both use the same atomic `save_config` from `src/config.py` |

## Decisions (answered 2026-10-17)
1. **Access:** site network only for v1 (any PC or phone on the site network). Remote
   access from outside (e.g. Tailscale) later if needed.
2. **Sites:** each site runs its own app at its own address. No central dashboard yet.
3. **Login:** one password per site. Task 11 is in scope.
4. **Online demo:** dropped. Task 12 removes Streamlit fully and the README demo link.
5. **Uncommitted work:** committed first (6ad7a7e) on branch `react-app`.
