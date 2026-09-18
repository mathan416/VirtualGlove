@echo off
setlocal
set "VG_ROOT=%LOCALAPPDATA%\VirtualGlove"
"%VG_ROOT%\runtime\Scripts\python.exe" -m virtualglove.launchbox_runtime ensure --settings "%VG_ROOT%\data\launcher.json"
"%VG_ROOT%\runtime\Scripts\python.exe" -m virtualglove.launchbox_hook --settings "%VG_ROOT%\data\launcher.json" "%~1"
exit /b %ERRORLEVEL%
