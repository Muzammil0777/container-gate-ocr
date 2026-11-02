@echo off
rem Installed sites: Windows starts this when the PC starts (task "Container Gate OCR", no sign-in needed).
rem It runs the detection service and the app, and restarts either one if it ever stops.
rem (ping is the 10-second wait: timeout needs a console window, which this task has none of.)
cd /d "%~dp0"
if not exist logs mkdir logs
if not exist cameras.json echo {}> cameras.json
if exist control_center.txt set /p GATE_CONTROL_CENTER=<control_center.txt
if "%1"=="detection" goto detection
start "" /b cmd /c ""%~f0" detection"
:app
echo [%date% %time%] starting the app>> logs\app.log
python\python.exe server.py >> logs\app.log 2>&1
ping -n 11 127.0.0.1 >nul
goto app
:detection
echo [%date% %time%] starting gate service>> logs\service.log
python\python.exe cctv.py --config cameras.json >> logs\service.log 2>&1
ping -n 11 127.0.0.1 >nul
goto detection
