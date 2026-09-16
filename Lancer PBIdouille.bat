@echo off
REM ===================================================================
REM  PBIdouille — double-clique ce fichier pour lancer l'application.
REM  Rien a installer d'autre que Python et PySide6 (ou PyQt5).
REM ===================================================================
setlocal
cd /d "%~dp0"

REM pythonw = pas de fenetre de console derriere l'application
set "PY="
where pythonw.exe >nul 2>&1 && set "PY=pythonw.exe"
if not defined PY where py.exe >nul 2>&1 && set "PY=py.exe -w"
if not defined PY where python.exe >nul 2>&1 && set "PY=python.exe"

if not defined PY (
    echo.
    echo   Python est introuvable sur cette machine.
    echo   Installe-le depuis https://www.python.org/downloads/
    echo   en cochant « Add Python to PATH », puis relance ce fichier.
    echo.
    pause
    exit /b 1
)

start "" %PY% "bidouille\app.py"
exit /b 0
