@echo off
rem Start the gate automatically when you sign in to Windows (no administrator rights needed).
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
(echo @echo off& echo start "" /min "%~dp0start_gate.bat") > "%STARTUP%\Container Gate OCR.bat"
echo Installed: the gate service and app now start when you sign in to Windows.
echo To undo, run uninstall_autostart.bat
pause
