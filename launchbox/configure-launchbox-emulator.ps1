param(
    [Parameter(Mandatory = $true)][string]$LaunchBoxRoot,
    [Parameter(Mandatory = $true)][string]$WrapperPath
)

$ErrorActionPreference = 'Stop'
if (Get-Process LaunchBox, BigBox -ErrorAction SilentlyContinue) {
    throw 'Close LaunchBox and Big Box before changing emulator associations.'
}
$dataFile = Join-Path $LaunchBoxRoot 'Data\Emulators.xml'
if (-not (Test-Path $dataFile -PathType Leaf)) {
    throw 'LaunchBox Data\Emulators.xml was not found. Start and close LaunchBox once, then rerun the installer.'
}
$document = New-Object System.Xml.XmlDocument
$document.PreserveWhitespace = $true
$document.Load($dataFile)
$root = $document.DocumentElement
$retroArch = @($root.Emulator | Where-Object { $_.Title -eq 'RetroArch' })
if ($retroArch.Count -ne 1) {
    throw 'LaunchBox must contain exactly one emulator named RetroArch before VirtualGlove can configure NES launches.'
}
$virtualGlove = @($root.Emulator | Where-Object { $_.Title -eq 'VirtualGlove RetroArch' })
if ($virtualGlove.Count -gt 1) {
    throw 'LaunchBox contains more than one VirtualGlove RetroArch emulator. Remove the duplicate and rerun the installer.'
}
$changed = $false
if ($virtualGlove.Count -eq 0) {
    $virtualGlove = $retroArch[0].CloneNode($true)
    $virtualGlove.ID = [guid]::NewGuid().ToString()
    $virtualGlove.Title = 'VirtualGlove RetroArch'
    $root.AppendChild($virtualGlove) | Out-Null
    $changed = $true
} else {
    $virtualGlove = $virtualGlove[0]
}
if ([string]$virtualGlove.ApplicationPath -ne $WrapperPath) {
    $virtualGlove.ApplicationPath = $WrapperPath
    $changed = $true
}
if ([string]$virtualGlove.CommandLine -ne '') {
    $virtualGlove.CommandLine = ''
    $changed = $true
}
$emulatorId = [string]$virtualGlove.ID
$nesAssociations = @($root.EmulatorPlatform | Where-Object { $_.Platform -eq 'Nintendo Entertainment System' })
$association = @($nesAssociations | Where-Object { $_.Emulator -eq $emulatorId })
if ($association.Count -gt 1) {
    throw 'LaunchBox contains duplicate VirtualGlove NES associations. Remove the duplicate and rerun the installer.'
}
if ($association.Count -eq 0) {
    $template = @($nesAssociations | Where-Object { $_.Emulator -eq [string]$retroArch[0].ID })
    if ($template.Count -ne 1) {
        throw 'The existing RetroArch NES association was not found uniquely.'
    }
    $association = $template[0].CloneNode($true)
    $association.Emulator = $emulatorId
    $association.CommandLine = ''
    $firstEmulator = @($root.Emulator) | Select-Object -First 1
    $root.InsertBefore($association, $firstEmulator) | Out-Null
    $changed = $true
} else {
    $association = $association[0]
}
foreach ($entry in @($root.EmulatorPlatform | Where-Object { $_.Platform -eq 'Nintendo Entertainment System' })) {
    $wanted = if ([string]$entry.Emulator -eq $emulatorId) { 'true' } else { 'false' }
    if ([string]$entry.Default -ne $wanted) {
        $entry.Default = $wanted
        $changed = $true
    }
}
if (-not $changed) {
    Write-Host 'PASS  VirtualGlove RetroArch is already the default NES emulator.'
    exit 0
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $env:LOCALAPPDATA "VirtualGlove\backups\$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$backupFile = Join-Path $backupRoot 'LaunchBox-Emulators.xml'
Copy-Item -LiteralPath $dataFile -Destination $backupFile
$temporary = Join-Path (Split-Path $dataFile) "Emulators.virtualglove-$stamp.tmp"
$document.Save($temporary)
[xml]$verification = Get-Content -Raw $temporary
$installed = @($verification.LaunchBox.Emulator | Where-Object { $_.Title -eq 'VirtualGlove RetroArch' })
$defaults = @($verification.LaunchBox.EmulatorPlatform | Where-Object { $_.Platform -eq 'Nintendo Entertainment System' -and $_.Default -eq 'true' })
if ($installed.Count -ne 1 -or $defaults.Count -ne 1 -or [string]$defaults[0].Emulator -ne $emulatorId) {
    Remove-Item -LiteralPath $temporary -Force
    throw 'The updated LaunchBox emulator definition did not validate; the original remains active.'
}
Move-Item -LiteralPath $temporary -Destination $dataFile -Force
try {
    [xml]$installedDocument = Get-Content -Raw $dataFile
    $installedDefault = @($installedDocument.LaunchBox.EmulatorPlatform | Where-Object { $_.Platform -eq 'Nintendo Entertainment System' -and $_.Default -eq 'true' })
    if ($installedDefault.Count -ne 1 -or [string]$installedDefault[0].Emulator -ne $emulatorId) {
        throw 'installed default did not match'
    }
} catch {
    Copy-Item -LiteralPath $backupFile -Destination $dataFile -Force
    throw 'LaunchBox verification failed after replacement; the backup was restored.'
}
Write-Host "PASS  VirtualGlove RetroArch is the default NES emulator; backup: $backupFile"
