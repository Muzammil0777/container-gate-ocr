# Container Gate OCR

Reads ISO 6346 container codes and Saudi plates from CCTV, logs each truck to SQLite + Excel.
Runs on a Windows site laptop, CPU only, no cloud. Users are gate staff, not developers.

## Layout
- `cctv.py`: detection service. `server.py`: FastAPI API + serves the React app from `web/dist`.
- `src/`: `gate.py` (truck logic), `store.py` (SQLite, Excel, corrections), `recognizer.py`/`scanner.py` (OCR),
  `iso6346.py`, `saudi_plate.py`, `camera.py` (NVR/RTSP), `config.py` (cameras.json), `i18n.py` (all UI text).
- `web/`: Vite + React + TypeScript + Mantine. `tasks/plan.md` + `tasks/todo.md`: current plan.

## Commands
- Tests: `py -3.12 -m pytest`
- App: `py -3.12 server.py --open` (http://localhost:8000). Detection: `py -3.12 cctv.py --config cameras.json`
- Web dev: `cd web && npm run dev`. Build: `cd web && npm run build`

## Rules
- Python 3.12 only (rapidocr doesn't support 3.13+).
- `web/dist` is committed so sites need no Node.js: after any `web/src` change, run the build and commit `web/dist`
  (on `react-app` only; task branches don't, see Parallel work).
- Every visible string goes in `src/i18n.py` with both `en` and `ar`; Arabic must work right-to-left.
  Exception: the Control Center (`control/`) is the developer's own tool, English only.
- UI text is plain language for gate staff. Explain terms like "check digit" with an (i).
- Never commit `cameras.json`, `logs/` or `videos/*.mp4` (NVR passwords, site data).
- `logs/gate.db` is the master record; Excel files are rebuilt from it. Don't write Excel as the source of truth.
- Big changes: plan in `tasks/plan.md`, then one task = one commit, tests passing before each commit.

## Parallel work (Orca worktrees)
Two sessions may run at once, each in its own worktree. Rounds and file ownership: `tasks/todo.md`, "Parallel work".
- Work on your own branch `task/<n>-<short-name>` made from `react-app`. Never commit on `react-app` or `main`,
  never push, never merge: the developer merges in the main folder.
- Do only the task(s) you were given. Touch only the files its `tasks/todo.md` entry lists, plus its tests.
  If you need another file (especially one the other session owns), stop and ask.
- Don't build or commit `web/dist`. Tick only your own task's boxes in `tasks/todo.md`; leave the rest of
  `tasks/plan.md` and `tasks/todo.md` alone.
- New strings in `src/i18n.py` go next to the strings of the same page, not at the end of the file.
- Run the app on your own port: session A `py -3.12 server.py --port 8001`, session B `--port 8002`.
  Port 8000 is the main app. Your worktree's `logs/` holds test data only.
- Never connect to the real NVR or cameras from a worktree (the recorder limits open streams, and a test
  could cut the live gate's view): use video files and the fake recorder. No real `cameras.json` here;
  if a test needs one, make one without passwords inside the worktree.
