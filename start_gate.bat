@echo off
rem Start the gate logger (cctv.py) and the dashboard (Streamlit app) together.
cd /d "%~dp0"
set PY=py -3.12
%PY% -c "import cv2, rapidocr_onnxruntime" 2>nul || set PY=python
if not exist cameras.json (
  echo cameras.json not found: copy cameras.example.json to cameras.json and fill in the NVR details.
  pause
  exit /b 1
)
start "Gate logger - close this window to stop logging" cmd /k %PY% cctv.py --config cameras.json
%PY% -m streamlit run app.py --server.port 8502
