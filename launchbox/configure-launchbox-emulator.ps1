param(
    [Parameter(Mandatory = $true)][string]$LaunchBoxRoot,
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [Parameter(Mandatory = $true)][string]$SettingsPath
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
$hookCommand = "-m virtualglove.launchbox_hook --settings `"$SettingsPath`""
if ([string]$virtualGlove.ApplicationPath -ne $PythonPath) {
    $virtualGlove.ApplicationPath = $PythonPath
    $changed = $true
}
if ([string]$virtualGlove.CommandLine -ne $hookCommand) {
    $virtualGlove.CommandLine = $hookCommand
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
$platformFile = Join-Path $LaunchBoxRoot 'Data\Platforms\Nintendo Entertainment System.xml'
if (-not (Test-Path $platformFile -PathType Leaf)) {
    throw 'LaunchBox Nintendo Entertainment System game data was not found.'
}
$gamesDocument = New-Object System.Xml.XmlDocument
$gamesDocument.PreserveWhitespace = $true
$gamesDocument.Load($platformFile)
$migratedGames = 0
foreach ($game in @($gamesDocument.DocumentElement.Game | Where-Object {
    $_.Platform -eq 'Nintendo Entertainment System' -and
    [string]$_.Emulator -eq [string]$retroArch[0].ID
})) {
    $game.Emulator = $emulatorId
    $migratedGames += 1
    $changed = $true
}
if (-not $changed) {
    Write-Host 'PASS  VirtualGlove RetroArch is already the default NES emulator for existing and new games.'
    exit 0
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $env:LOCALAPPDATA "VirtualGlove\backups\$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$backupFile = Join-Path $backupRoot 'LaunchBox-Emulators.xml'
$gamesBackupFile = Join-Path $backupRoot 'LaunchBox-Nintendo-Entertainment-System.xml'
Copy-Item -LiteralPath $dataFile -Destination $backupFile
Copy-Item -LiteralPath $platformFile -Destination $gamesBackupFile
$temporary = Join-Path (Split-Path $dataFile) "Emulators.virtualglove-$stamp.tmp"
$gamesTemporary = Join-Path (Split-Path $platformFile) "Nintendo Entertainment System.virtualglove-$stamp.tmp"
$document.Save($temporary)
$gamesDocument.Save($gamesTemporary)
[xml]$verification = Get-Content -Raw $temporary
$gamesVerification = New-Object System.Xml.XmlDocument
$gamesVerification.Load($gamesTemporary)
$installed = @($verification.LaunchBox.Emulator | Where-Object { $_.Title -eq 'VirtualGlove RetroArch' })
$defaults = @($verification.LaunchBox.EmulatorPlatform | Where-Object { $_.Platform -eq 'Nintendo Entertainment System' -and $_.Default -eq 'true' })
if ($installed.Count -ne 1 -or $defaults.Count -ne 1 -or [string]$defaults[0].Emulator -ne $emulatorId -or
    @($gamesVerification.DocumentElement.Game | Where-Object {
        $_.Platform -eq 'Nintendo Entertainment System' -and
        [string]$_.Emulator -eq [string]$retroArch[0].ID
    }).Count -ne 0) {
    Remove-Item -LiteralPath $temporary -Force
    Remove-Item -LiteralPath $gamesTemporary -Force
    throw 'The updated LaunchBox emulator definition did not validate; the original remains active.'
}
try {
    Move-Item -LiteralPath $temporary -Destination $dataFile -Force
    Move-Item -LiteralPath $gamesTemporary -Destination $platformFile -Force
    [xml]$installedDocument = Get-Content -Raw $dataFile
    [xml]$installedGames = Get-Content -Raw $platformFile
    $installedDefault = @($installedDocument.LaunchBox.EmulatorPlatform | Where-Object { $_.Platform -eq 'Nintendo Entertainment System' -and $_.Default -eq 'true' })
    $oldAssignments = @($installedGames.LaunchBox.Game | Where-Object {
        $_.Platform -eq 'Nintendo Entertainment System' -and
        [string]$_.Emulator -eq [string]$retroArch[0].ID
    })
    if ($installedDefault.Count -ne 1 -or [string]$installedDefault[0].Emulator -ne $emulatorId -or
        $oldAssignments.Count -ne 0) {
        throw 'installed default did not match'
    }
} catch {
    Copy-Item -LiteralPath $backupFile -Destination $dataFile -Force
    Copy-Item -LiteralPath $gamesBackupFile -Destination $platformFile -Force
    throw 'LaunchBox verification failed after replacement; the backup was restored.'
}
Write-Host "PASS  VirtualGlove RetroArch is the default NES emulator; migrated $migratedGames existing standard RetroArch games; backup: $backupRoot"
