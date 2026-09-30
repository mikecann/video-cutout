param(
    [string]$ToolsDir = 'C:\dev\tools',
    [string]$ClassesRoot = 'HKCU:\Software\Classes',
    [string]$IconDir = "$env:LOCALAPPDATA\video-cutout\icons"
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This uninstaller requires Windows.' }
. (Join-Path $PSScriptRoot 'install-lib.ps1')

foreach ($ext in $VideoExtensions) {
    $verb = "$ClassesRoot\SystemFileAssociations\$ext\shell\MikesTools\shell\VideoCutout"
    if (Test-Path $verb) { Remove-Item -Path $verb -Recurse -Force }
}
foreach ($name in @('video-cutout.bat', 'video-cutout')) {
    $path = Join-Path $ToolsDir $name
    if (Test-Path $path) { Remove-Item -Path $path -Force }
}
$icon = Join-Path $IconDir 'video-cutout.ico'
if (Test-Path $icon) { Remove-Item -Path $icon -Force }

# Keep the shared menu, PATH, source clone, Python environment and model downloads.
Write-Host 'Uninstalled video-cutout launchers and Explorer entries.' -ForegroundColor Green
