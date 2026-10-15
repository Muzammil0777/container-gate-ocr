@echo off
rem Check the connection to the Hikvision NVR and save a snapshot of every camera channel.
cd /d "%~dp0"
set PY=py -3.12
%PY% -c "import cv2, rapidocr_onnxruntime" 2>nul || set PY=python
if exist cameras.json (%PY% cctv.py --scan --config cameras.json) else (%PY% cctv.py --scan)
pause
