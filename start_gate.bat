@echo off
rem Start the gate: the detection service (minimised window) and the app in your browser.
cd /d "%~dp0"
start "Gate detection service - keep open" /min cmd /c run_service.bat
set PY=py -3.12
%PY% -c "import cv2, rapidocr_onnxruntime" 2>nul || set PY=python
%PY% -m streamlit run app.py --server.port 8502
