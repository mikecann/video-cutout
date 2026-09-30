# Run from this clone. Only launchers and model downloads live in C:\dev\tools.
param(
    [switch]$SkipDeps,
    [string]$ToolsDir = 'C:\dev\tools',
    [string]$ClassesRoot = 'HKCU:\Software\Classes',
    [string]$IconDir = "$env:LOCALAPPDATA\video-cutout\icons"
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This installer requires Windows.' }
$RepoDir = $PSScriptRoot
. (Join-Path $RepoDir 'install-lib.ps1')

New-Item -ItemType Directory -Path $ToolsDir -Force | Out-Null
New-Item -ItemType Directory -Path $IconDir -Force | Out-Null
Write-BatStub $ToolsDir $RepoDir
$icon = Join-Path $IconDir 'video-cutout.ico'
ConvertTo-Ico (Join-Path $RepoDir 'icons\film.png') $icon

$launcher = Join-Path $ToolsDir 'video-cutout.bat'
$command = 'cmd.exe /k ""{0}" "%1""' -f $launcher
foreach ($ext in $VideoExtensions) {
    $root = "$ClassesRoot\SystemFileAssociations\$ext\shell\MikesTools"
    Set-MikesToolsRoot $root
    Add-MikesVerb $root $icon $command

    # Replace this tool's old entry without touching neighbouring menu verbs.
    $legacyVerb = "$root\shell\RemovePortrait"
    $legacyCommand = "$legacyVerb\command"
    if (Test-Path $legacyCommand) {
        $value = (Get-Item $legacyCommand).GetValue('')
        if ($value -like '*\remove-portrait.bat*') {
            Remove-Item -Path $legacyVerb -Recurse -Force
        }
    }
}

if (-not (($env:PATH -split ';') | Where-Object { $_.TrimEnd('\') -ieq $ToolsDir.TrimEnd('\') })) {
    Write-Host "Add '$ToolsDir' to your User PATH, then open a new terminal." -ForegroundColor Yellow
}

if (-not $SkipDeps) { & (Join-Path $RepoDir 'deps.ps1') }
Write-Host "Installed video-cutout from $RepoDir" -ForegroundColor Green
