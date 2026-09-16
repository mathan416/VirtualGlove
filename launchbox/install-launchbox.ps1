param(
    [Parameter(Mandatory = $true)][string]$LaunchBoxRoot,
    [Parameter(Mandatory = $true)][string]$RetroArchRoot,
    [string]$ControllerHost
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA "VirtualGlove"
$DataRoot = Join-Path $InstallRoot "data"
$RuntimeRoot = Join-Path $InstallRoot "runtime"
$LaunchBoxFiles = Join-Path $InstallRoot "launchbox"
$NativeRoot = Join-Path $InstallRoot "native"
$Python = Join-Path $RuntimeRoot "Scripts\python.exe"
$RetroArch = Join-Path $RetroArchRoot "retroarch.exe"
$Fceumm = Join-Path $RetroArchRoot "cores\fceumm_libretro.dll"
$Native = Join-Path $NativeRoot "nestopia_powerglove_libretro.dll"
$Registry = Join-Path $DataRoot "games.json"
$Token = Join-Path $DataRoot "token"
$Settings = Join-Path $DataRoot "launcher.json"
$NativeState = Join-Path $InstallRoot "run\native-state.bin"
$RetroConfig = Join-Path $LaunchBoxFiles "retroarch-nes.cfg"

if (-not [Environment]::Is64BitOperatingSystem) { throw "LaunchBox support requires 64-bit Windows." }
if (-not (Test-Path $LaunchBoxRoot -PathType Container)) { throw "LaunchBox folder was not found." }
if (-not (Test-Path $RetroArch -PathType Leaf)) { throw "retroarch.exe was not found." }
if (-not (Test-Path $Fceumm -PathType Leaf)) { throw "The FCEUmm core was not found." }
if (-not (Test-Path $Python -PathType Leaf) -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Install 64-bit Python 3 for Windows, including the py launcher, then run this installer again."
}

New-Item -ItemType Directory -Force -Path $InstallRoot, $DataRoot, $LaunchBoxFiles, $NativeRoot, (Split-Path $NativeState) | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "virtualglove-launchbox.cmd") $LaunchBoxFiles
Copy-Item -Force (Join-Path $PSScriptRoot "virtualglove-pair.ps1") $LaunchBoxFiles
Copy-Item -Force (Join-Path $PSScriptRoot "retroarch-nes.cfg") $LaunchBoxFiles

if (-not (Test-Path $Python -PathType Leaf)) {
    py -3 -m venv $RuntimeRoot
}
& $Python -m pip install --disable-pip-version-check --upgrade "$SourceRoot[launchbox]"

if (-not (Test-Path $Registry -PathType Leaf)) {
    Copy-Item (Join-Path $SourceRoot "config\games.json") $Registry
}
if (-not (Test-Path $Token -PathType Leaf)) {
    New-Item -ItemType File -Path $Token | Out-Null
}
$ExistingConfig = $null
if (Test-Path $Settings -PathType Leaf) {
    $ExistingConfig = Get-Content -Raw $Settings | ConvertFrom-Json
}
if (-not $PSBoundParameters.ContainsKey("ControllerHost")) {
    if ($ExistingConfig -and $ExistingConfig.uno_q) {
        $ControllerHost = [string]$ExistingConfig.uno_q
    } else {
        $ControllerHost = "virtualglove.local"
    }
}
if ([string]::IsNullOrWhiteSpace($ControllerHost)) {
    throw "ControllerHost must be a hostname or IP address."
}
$BundledCore = Join-Path $SourceRoot "native\launchbox\x86_64\nestopia_powerglove_libretro.dll"
$BundledSource = Join-Path $SourceRoot "native\launchbox\x86_64\nestopia-powerglove-source.tar.gz"
$ManifestPath = Join-Path $SourceRoot "native\launchbox\manifest.json"
if (-not (Test-Path $BundledCore -PathType Leaf) -or
    -not (Test-Path $BundledSource -PathType Leaf) -or
    -not (Test-Path $ManifestPath -PathType Leaf)) {
    throw "The reviewed Windows core, corresponding source, or manifest is missing from this package."
}
$Manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json
$CoreHash = (Get-FileHash -Algorithm SHA256 $BundledCore).Hash.ToLowerInvariant()
$SourceHash = (Get-FileHash -Algorithm SHA256 $BundledSource).Hash.ToLowerInvariant()
if ($Manifest.target -ne "launchbox-x86_64" -or
    $Manifest.architecture -ne "x86_64" -or
    $Manifest.core_sha256 -ne $CoreHash -or
    $Manifest.core_size -ne (Get-Item $BundledCore).Length -or
    $Manifest.source_sha256 -ne $SourceHash -or
    $Manifest.source_size -ne (Get-Item $BundledSource).Length) {
    throw "The Windows x86-64 native-core manifest did not match the packaged DLL and source."
}
& $Python (Join-Path $SourceRoot "scripts\verify-launchbox-native-core.py") --core $BundledCore
if (Test-Path $BundledCore -PathType Leaf) {
    Copy-Item -Force $BundledCore $Native
}

$Config = [ordered]@{
    uno_q = $ControllerHost
    port = 55356
    token_file = $Token
    registry = $Registry
    timeout = 0.4
    retroarch = $RetroArch
    fceumm_core = $Fceumm
    native_core = $Native
    native_state = $NativeState
    retroarch_config = $RetroConfig
    heartbeat_seconds = 2.0
    lease_seconds = 6.0
}
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($Settings, ($Config | ConvertTo-Json), $Utf8NoBom)

& $Python -m powerglove_vision.launchbox_runtime ensure --settings $Settings

Write-Host "VirtualGlove LaunchBox support installed for this Windows user."
Write-Host "Windows may ask whether Python can listen on the network; allow Private networks only."
Write-Host "Pair from Controller Setup using the LaunchBox one-time-code command."
Write-Host "In LaunchBox, add an emulator named VirtualGlove RetroArch."
Write-Host "Set its application path to: $LaunchBoxFiles\virtualglove-launchbox.cmd"
Write-Host "Associate Nintendo Entertainment System and use the ROM file as the only parameter."
