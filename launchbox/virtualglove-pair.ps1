$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "VirtualGlove"
$Python = Join-Path $Root "runtime\Scripts\python.exe"
$Restart = Join-Path $Root "launchbox\virtualglove-restart-runtime.cmd"
& $Python -m virtualglove.pairing `
    --token-file (Join-Path $Root "data\token") `
    --receiver-restart-command $Restart
exit $LASTEXITCODE
