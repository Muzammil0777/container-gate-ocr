@echo off
title Gate app - keep this window open
rem Start the gate: the detection service (minimised window) and the app, which opens in your browser.
rem Other computers and phones on the network use the address shown below, once a site password is set.
cd /d "%~dp0"
start "Gate detection service - keep open" /min cmd /c run_service.bat
set PY=py -3.12
%PY% -c "import cv2, rapidocr_onnxruntime" 2>nul || set PY=python
set OPEN=--open
:loop
%PY% server.py %OPEN%
set OPEN=
echo [%date% %time%] The gate app stopped. Starting it again in 10 seconds (close this window to stop it).
timeout /t 10 /nobreak >nul
goto loop
