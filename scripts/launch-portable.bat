@echo off
title Nous Companion
echo.
echo  ⬡ NOUS COMPANION
echo  Portable Launcher
echo.
echo  Detecting Hermes environment...
where wsl.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    wsl.exe sh -lc "test -d \"$HOME/.hermes\"" >nul 2>&1
    if %ERRORLEVEL%==0 (
        set NOUS_COMPANION_BACKEND_MODE=wsl
        echo  ✓ WSL Hermes install detected — backend mode: WSL
    ) else (
        echo  - WSL available but no Hermes found — using native Python
    )
) else (
    echo  - WSL not available — using native Python
)
echo.
echo  Starting companion...
echo  Open http://localhost:8765 in your browser when ready.
echo.
start "" "%~dp0nous-companion.exe"
echo.
echo  To close the companion, close this window and the app.
pause
