@echo off
rem Start the app. Start cameras in its Live tab; cameras saved there start automatically.
rem (For logging without the app, run: py -3.12 cctv.py --config cameras.json)
cd /d "%~dp0"
set PY=py -3.12
%PY% -c "import cv2, rapidocr_onnxruntime" 2>nul || set PY=python
%PY% -m streamlit run app.py --server.port 8502
