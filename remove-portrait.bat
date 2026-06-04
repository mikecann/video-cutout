@echo off
setlocal

if "%~1"=="" (
    echo Usage: remove-portrait ^<video_file^> [options]
    echo Example: remove-portrait C:\videos\clip.mkv --preview --sample-seconds 3
    exit /b 1
)

python "%~dp0remove_portrait.py" %*
