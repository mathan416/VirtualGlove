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
$InstalledNativeManifest = Join-Path $NativeRoot "manifest.json"
$InstalledNativeSource = Join-Path $NativeRoot "nestopia-powerglove-source.tar.gz"
$Registry = Join-Path $DataRoot "games.json"
$Token = Join-Path $DataRoot "token"
$Settings = Join-Path $DataRoot "launcher.json"
$NativeState = Join-Path $InstallRoot "run\native-state.bin"
$RetroConfig = Join-Path $LaunchBoxFiles "retroarch-nes.cfg"
$RetroNativeConfig = Join-Path $LaunchBoxFiles "retroarch-native.cfg"
$RetroMainConfig = Join-Path $RetroArchRoot "retroarch.cfg"
$InputWarning = Join-Path $DataRoot "input-warning.txt"

if (-not [Environment]::Is64BitOperatingSystem) { throw "LaunchBox support requires 64-bit Windows." }
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer from PowerShell as Administrator so it can isolate RetroArch's local input port."
}
if (-not (Test-Path $LaunchBoxRoot -PathType Container)) { throw "LaunchBox folder was not found." }
if (-not (Test-Path $RetroArch -PathType Leaf)) { throw "retroarch.exe was not found." }
if (-not (Test-Path $Fceumm -PathType Leaf)) { throw "The FCEUmm core was not found." }
if (Get-Process LaunchBox, BigBox, retroarch -ErrorAction SilentlyContinue) {
    throw "Close LaunchBox, Big Box, and RetroArch before installing or upgrading VirtualGlove."
}
if (-not (Test-Path $Python -PathType Leaf) -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Install 64-bit Python 3 for Windows, including the py launcher, then run this installer again."
}

New-Item -ItemType Directory -Force -Path $InstallRoot, $DataRoot, $LaunchBoxFiles, $NativeRoot, (Split-Path $NativeState) | Out-Null

# An older installation may have started the same services from a system
# Python. Stop only VirtualGlove's background services before replacing the
# managed runtime so one receiver owns the input port after the upgrade.
$InstallPattern = [regex]::Escape($InstallRoot)
$LegacyModule = "power" + "glove_vision"
$BackgroundModules = "(virtualglove|$LegacyModule)\.(launchbox_runtime|receiver|game_registry)"
function Get-VirtualGloveBackgroundServices {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine -match $InstallPattern -and
        $_.CommandLine -match $BackgroundModules
    })
}
$StopDeadline = (Get-Date).AddSeconds(8)
$QuietScans = 0
do {
    $ExistingServices = @(Get-VirtualGloveBackgroundServices)
    if ($ExistingServices.Count -eq 0) {
        $QuietScans += 1
    } else {
        $QuietScans = 0
        foreach ($Process in $ExistingServices) {
            # A receiver may finish normally after the process snapshot but
            # before this command runs. The next scan proves whether it is gone.
            Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    if ($QuietScans -lt 4) { Start-Sleep -Milliseconds 250 }
} while ($QuietScans -lt 4 -and (Get-Date) -lt $StopDeadline)
$RemainingServices = @(Get-VirtualGloveBackgroundServices)
if ($QuietScans -lt 4 -or $RemainingServices.Count -gt 0) {
    throw "Could not stop VirtualGlove's existing background services. Restart Windows, then run this installer again."
}

Copy-Item -Force (Join-Path $PSScriptRoot "virtualglove-launchbox.cmd") $LaunchBoxFiles
Copy-Item -Force (Join-Path $PSScriptRoot "virtualglove-pair.ps1") $LaunchBoxFiles
Copy-Item -Force (Join-Path $PSScriptRoot "virtualglove-restart-runtime.cmd") $LaunchBoxFiles
Copy-Item -Force (Join-Path $PSScriptRoot "configure-launchbox-emulator.ps1") $LaunchBoxFiles

if (-not (Test-Path $Python -PathType Leaf)) {
    py -3 -m venv $RuntimeRoot
}
$LegacyDistribution = "power" + "glove-vision"
& $Python -m pip uninstall --disable-pip-version-check -y $LegacyDistribution | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not remove the retired VirtualGlove Python distribution." }
& $Python -m pip install --disable-pip-version-check --upgrade "$SourceRoot[launchbox]"
if ($LASTEXITCODE -ne 0) { throw "Could not install the current VirtualGlove Python distribution." }
$LegacyCommands = "power" + "glove-"
# Some development and 0.4.x installations used the current distribution name
# while still installing the retired module directory. Pip removes its recorded
# files during the upgrade, but generated bytecode and local diagnostic backups
# can leave the directory behind. It is wholly inside VirtualGlove's managed
# virtual environment, so remove only these exact retired runtime paths after
# the current package has installed successfully.
$LegacyModuleRoot = Join-Path $RuntimeRoot "Lib\site-packages\$LegacyModule"
if (Test-Path $LegacyModuleRoot) {
    Remove-Item -LiteralPath $LegacyModuleRoot -Recurse -Force
}
Get-ChildItem -LiteralPath (Join-Path $RuntimeRoot "Scripts") -Filter "$LegacyCommands*" `
    -Force -ErrorAction SilentlyContinue | Remove-Item -Force
$RetiredRuntime = @(Get-ChildItem -Path $RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -like "*$LegacyModule*" -or $_.Name -like "$LegacyCommands*"
})
if ($RetiredRuntime.Count -gt 0) {
    throw "The retired VirtualGlove Python distribution was not completely removed."
}

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
function Test-RetroPadPortAvailable {
    param([Parameter(Mandatory = $true)][int]$Port)
    $Probe = $null
    try {
        $Probe = [Net.Sockets.UdpClient]::new([Net.Sockets.AddressFamily]::InterNetwork)
        $Probe.Client.ExclusiveAddressUse = $true
        $Probe.Client.Bind([Net.IPEndPoint]::new([Net.IPAddress]::Loopback, $Port))
        return $true
    } catch [Net.Sockets.SocketException] {
        # Hyper-V, WSL, and other Windows components can reserve high port
        # ranges without creating a visible UDP endpoint. A real bind is the
        # authoritative availability check.
        return $false
    } finally {
        if ($null -ne $Probe) { $Probe.Dispose() }
    }
}
$RemotePort = 0
if ($ExistingConfig -and $ExistingConfig.retroarch_remote_port) {
    $Candidate = [int]$ExistingConfig.retroarch_remote_port
    if ($Candidate -ge 49152 -and $Candidate -le 65535) { $RemotePort = $Candidate }
}
while ($RemotePort -eq 0 -or -not (Test-RetroPadPortAvailable -Port $RemotePort)) {
    $RemotePort = Get-Random -Minimum 49152 -Maximum 65536
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
& $Python (Join-Path $SourceRoot "scripts\verify-launchbox-native-core.py") --core $BundledCore --load
if (Test-Path $BundledCore -PathType Leaf) {
    Copy-Item -Force $BundledCore $Native
    Copy-Item -Force $ManifestPath $InstalledNativeManifest
    Copy-Item -Force $BundledSource $InstalledNativeSource
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$StandardConfig = Get-Content -Raw (Join-Path $PSScriptRoot "retroarch-nes.cfg")
$StandardConfig += "`nnetwork_remote_base_port = `"$RemotePort`"`n"
[System.IO.File]::WriteAllText($RetroConfig, $StandardConfig, $Utf8NoBom)
Copy-Item -Force (Join-Path $PSScriptRoot "retroarch-native.cfg") $RetroNativeConfig

$FirewallName = "VirtualGlove LaunchBox RetroPad isolation"
Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $FirewallName -Direction Inbound -Action Block `
    -Protocol UDP -LocalPort $RemotePort -RemoteAddress LocalSubnet -Profile Any `
    -Program $RetroArch | Out-Null
$FirewallRule = Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction Stop
$FirewallPort = $FirewallRule | Get-NetFirewallPortFilter
$FirewallAddress = $FirewallRule | Get-NetFirewallAddressFilter
if ($FirewallRule.Enabled -ne "True" -or $FirewallRule.Action -ne "Block" -or
    $FirewallPort.Protocol -ne "UDP" -or [int]$FirewallPort.LocalPort -ne $RemotePort -or
    @($FirewallAddress.RemoteAddress) -notcontains "LocalSubnet") {
    throw "The managed RetroArch input-isolation firewall rule did not validate."
}
& $Python -m virtualglove.retroarch_remote --check-loopback $RemotePort
if ($LASTEXITCODE -ne 0) { throw "RetroArch loopback input validation failed." }

$Config = [ordered]@{
    uno_q = $ControllerHost
    port = 55356
    token_file = $Token
    registry = $Registry
    timeout = 0.4
    retroarch = $RetroArch
    fceumm_core = $Fceumm
    native_core = $Native
    native_core_sha256 = $CoreHash
    native_state = $NativeState
    input_route = "network-retropad"
    retroarch_remote_port = $RemotePort
    retroarch_config = $RetroConfig
    retroarch_native_config = $RetroNativeConfig
    retroarch_main_config = $RetroMainConfig
    input_warning = $InputWarning
    heartbeat_seconds = 2.0
    lease_seconds = 6.0
}
[System.IO.File]::WriteAllText($Settings, ($Config | ConvertTo-Json), $Utf8NoBom)

& $Python -m virtualglove.retroarch_hotkeys --config $RetroMainConfig --config $RetroConfig
if ($LASTEXITCODE -ne 0) {
    Write-Warning "The manual keyboard backup has a RetroArch hotkey conflict. VirtualGlove RetroPad and the physical controller remain usable."
}

& (Join-Path $LaunchBoxFiles "configure-launchbox-emulator.ps1") `
    -LaunchBoxRoot $LaunchBoxRoot -PythonPath $Python -SettingsPath $Settings

& $Python -m virtualglove.launchbox_runtime ensure --settings $Settings

Write-Host "VirtualGlove LaunchBox support installed for this Windows user."
Write-Host "Windows may ask whether Python can listen on the network; allow Private networks only."
Write-Host "Pair from Controller Setup using the LaunchBox one-time-code command."
Write-Host "VirtualGlove RetroArch is the default Nintendo Entertainment System emulator."
Write-Host "Input route: local Network RetroPad on UDP $RemotePort; LAN access is blocked."
Write-Host "Existing NES games using standard RetroArch and new imports use it automatically; other emulator overrides remain explicit."
