@echo off
setlocal
if not defined EXEDIR set "EXEDIR=%~dp0"

if "%~1"=="" (
    echo Usage: video-cutout ^<video_file^> [options]
    echo Example: video-cutout C:\videos\clip.mkv --sample-seconds 3 --max-width 960
    exit /b 1
)

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0video_cutout.py" %*
) else (
    python "%~dp0video_cutout.py" %*
)
