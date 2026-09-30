# Shared by install and uninstall so the registered extensions stay in sync.
$VideoExtensions = @('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.m4v', '.mpg', '.mpeg', '.ts', '.mts', '.m2ts', '.flv', '.f4v')

function Write-BatStub($ToolsDir, $RepoDir) {
    $content = @"
@echo off
setlocal
set "EXEDIR=%~dp0"
call "$RepoDir\video-cutout.bat" %*
"@
    Set-Content -Path (Join-Path $ToolsDir 'video-cutout.bat') -Value $content -Encoding ASCII

    # Git Bash users get the same command without typing the .bat extension.
    $bash = @'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/video-cutout.bat" "$@"
'@
    Set-Content -Path (Join-Path $ToolsDir 'video-cutout') -Value $bash -Encoding ASCII
}

# PNG-in-ICO preserves alpha, unlike GetHicon()/Icon.FromHandle().
function ConvertTo-Ico($PngPath, $IcoPath) {
    $pngBytes = [System.IO.File]::ReadAllBytes($PngPath)
    $stream = [System.IO.FileStream]::new($IcoPath, [System.IO.FileMode]::Create)
    $writer = [System.IO.BinaryWriter]::new($stream)
    try {
        $writer.Write([uint16]0)
        $writer.Write([uint16]1)
        $writer.Write([uint16]1)
        $writer.Write([byte]16)
        $writer.Write([byte]16)
        $writer.Write([byte]0)
        $writer.Write([byte]0)
        $writer.Write([uint16]1)
        $writer.Write([uint16]32)
        $writer.Write([uint32]$pngBytes.Length)
        $writer.Write([uint32]22)
        $writer.Write($pngBytes)
    } finally {
        $writer.Dispose()
    }
}

function Set-MikesToolsRoot($RootKey) {
    # Existing roots belong to all the tools that use this menu. Leave them alone.
    if (Test-Path $RootKey) { return }
    New-Item -Path $RootKey -Force | Out-Null
    Set-ItemProperty -Path $RootKey -Name 'MUIVerb' -Value "Mike's Tools"
    Set-ItemProperty -Path $RootKey -Name 'SubCommands' -Value ''
    # A system icon survives uninstalling any one tool that uses the shared root.
    Set-ItemProperty -Path $RootKey -Name 'Icon' -Value '%SystemRoot%\System32\shell32.dll,71'
}

function Add-MikesVerb($RootKey, $Icon, $Command) {
    $verbKey = "$RootKey\shell\VideoCutout"
    New-Item -Path $verbKey -Force | Out-Null
    New-Item -Path "$verbKey\command" -Force | Out-Null
    Set-ItemProperty -Path $verbKey -Name 'MUIVerb' -Value 'Video Cutout'
    Set-ItemProperty -Path $verbKey -Name 'Icon' -Value $Icon
    Set-ItemProperty -Path "$verbKey\command" -Name '(Default)' -Value $Command
}
