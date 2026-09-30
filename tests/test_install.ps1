# Exercise the real registry provider on Windows, under a disposable test key.
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Installer integration tests require Windows.' }
$repo = Split-Path -Parent $PSScriptRoot
$id = [guid]::NewGuid().ToString('N')
$temp = Join-Path ([System.IO.Path]::GetTempPath()) "video-cutout-test-$id"
$classes = "HKCU:\Software\VideoCutoutInstallerTests\$id"
$tools = Join-Path $temp 'tools with spaces'
$icons = Join-Path $temp 'icons'
$options = @{ SkipDeps = $true; ToolsDir = $tools; ClassesRoot = $classes; IconDir = $icons }

function Assert-True($Condition, $Message) {
    if (-not $Condition) { throw $Message }
}

try {
    $root = "$classes\SystemFileAssociations\.mov\shell\MikesTools"
    New-Item -Path "$root\shell\OtherTool\command" -Force | Out-Null
    Set-ItemProperty -Path $root -Name 'MUIVerb' -Value "Mike's Tools"
    Set-ItemProperty -Path $root -Name 'SubCommands' -Value ''
    Set-ItemProperty -Path $root -Name 'Icon' -Value 'existing-shared.ico'
    Set-ItemProperty -Path "$root\shell\OtherTool\command" -Name '(Default)' -Value 'other.exe'
    New-Item -Path "$root\shell\RemovePortrait\command" -Force | Out-Null
    Set-ItemProperty -Path "$root\shell\RemovePortrait\command" -Name '(Default)' -Value 'cmd.exe /k ""C:\dev\tools\remove-portrait.bat" "%1""'

    # Two installs must preserve existing roots and the other tool's command.
    & "$repo\install.ps1" @options
    & "$repo\install.ps1" @options
    Assert-True ((Get-Item $root).GetValue('Icon') -eq 'existing-shared.ico') 'Shared icon changed.'
    Assert-True ((Get-Item "$root\shell\OtherTool\command").GetValue('') -eq 'other.exe') 'Other tool changed.'
    Assert-True (-not (Test-Path "$root\shell\RemovePortrait")) 'Old verb was not replaced.'

    . "$repo\install-lib.ps1"
    foreach ($ext in $VideoExtensions) {
        $menu = "$classes\SystemFileAssociations\$ext\shell\MikesTools"
        Assert-True ((Get-Item $menu).GetValue('MUIVerb') -eq "Mike's Tools") "Missing menu for $ext."
        $actual = (Get-Item "$menu\shell\VideoCutout\command").GetValue('')
        $expected = 'cmd.exe /k ""{0}" "%1""' -f (Join-Path $tools 'video-cutout.bat')
        Assert-True ($actual -eq $expected) "Incorrect command quoting for $ext."
    }
    $bat = Get-Content (Join-Path $tools 'video-cutout.bat') -Raw
    Assert-True ($bat.Contains("call `"$repo\video-cutout.bat`" %*")) 'Stub does not forward arguments to this clone.'
    Assert-True ($bat.Contains('set "EXEDIR=%~dp0"')) 'Stub does not pass its binary directory.'
    $batBytes = [System.IO.File]::ReadAllBytes((Join-Path $tools 'video-cutout.bat'))
    Assert-True (@($batBytes | Where-Object { $_ -gt 127 }).Count -eq 0) 'Stub is not ASCII.'
    Assert-True (Test-Path (Join-Path $tools 'video-cutout')) 'Git Bash wrapper is missing.'
    $ico = [System.IO.File]::ReadAllBytes((Join-Path $icons 'video-cutout.ico'))
    Assert-True ($ico.Length -gt 22 -and $ico[2] -eq 1 -and $ico[4] -eq 1) 'Invalid ICO header.'

    # Unrelated files and registry entries must survive repeated uninstall.
    New-Item -ItemType File -Path (Join-Path $tools 'other.bat') -Force | Out-Null
    $options.Remove('SkipDeps')
    & "$repo\uninstall.ps1" @options
    & "$repo\uninstall.ps1" @options
    foreach ($ext in $VideoExtensions) {
        $menu = "$classes\SystemFileAssociations\$ext\shell\MikesTools"
        Assert-True (Test-Path $menu) 'Shared menu was deleted.'
        Assert-True (-not (Test-Path "$menu\shell\VideoCutout")) 'Own verb survived uninstall.'
    }
    Assert-True ((Get-Item "$root\shell\OtherTool\command").GetValue('') -eq 'other.exe') 'Uninstall removed another tool.'
    Assert-True (Test-Path (Join-Path $tools 'other.bat')) 'Uninstall removed another launcher.'
    foreach ($name in @('video-cutout.bat', 'video-cutout')) {
        Assert-True (-not (Test-Path (Join-Path $tools $name))) 'Own launcher survived uninstall.'
    }
    Assert-True (-not (Test-Path (Join-Path $icons 'video-cutout.ico'))) 'Own icon survived uninstall.'
    Write-Host 'Installer integration tests passed.' -ForegroundColor Green
} finally {
    if (Test-Path $classes) { Remove-Item -Path $classes -Recurse -Force }
    if (Test-Path $temp) { Remove-Item -Path $temp -Recurse -Force }
}
