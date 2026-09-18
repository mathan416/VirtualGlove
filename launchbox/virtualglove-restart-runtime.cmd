@echo off
setlocal
set "VG_ROOT=%LOCALAPPDATA%\VirtualGlove"
"%VG_ROOT%\runtime\Scripts\python.exe" -m powerglove_vision.launchbox_runtime restart --settings "%VG_ROOT%\data\launcher.json"
exit /b %ERRORLEVEL%
