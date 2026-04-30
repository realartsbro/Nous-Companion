@echo off
title Nous Companion
echo.
echo  ⬡ NOUS COMPANION
echo  Portable Launcher
echo.
echo  The companion needs to know how to reach your Hermes install.
echo.
set /p USE_WSL=" Are you using Hermes inside WSL? (y/N): "
if /i "%USE_WSL%"=="y" (
    set NOUS_COMPANION_BACKEND_MODE=wsl
    echo  Backend mode: WSL
) else (
    echo  Backend mode: Windows (native)
)
echo.
echo  Starting companion...
echo  Open http://localhost:8765 in your browser when ready.
echo.
start "" "%~dp0nous-companion.exe"
echo.
echo  To close the companion, close this window and the app.
pause
