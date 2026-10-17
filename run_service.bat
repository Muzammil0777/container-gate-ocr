@echo off
rem Gate detection service. Restarts itself if it ever stops (camera drop-outs are handled inside).
cd /d "%~dp0"
set PY=py -3.12
%PY% -c "import cv2, rapidocr_onnxruntime" 2>nul || set PY=python
if not exist logs mkdir logs
if not exist cameras.json echo {}> cameras.json
:loop
echo [%date% %time%] starting gate service>> logs\service.log
%PY% cctv.py --config cameras.json >> logs\service.log 2>&1
timeout /t 10 /nobreak >nul
goto loop
