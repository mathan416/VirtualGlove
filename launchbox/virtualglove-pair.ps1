$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "VirtualGlove"
$Python = Join-Path $Root "runtime\Scripts\python.exe"
$Settings = Join-Path $Root "data\launcher.json"
& $Python -m powerglove_vision.pairing `
    --token-file (Join-Path $Root "data\token") `
    --receiver-restart-command $Python -m powerglove_vision.launchbox_runtime restart --settings $Settings
exit $LASTEXITCODE
