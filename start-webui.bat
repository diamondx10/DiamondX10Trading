@echo off
REM Start the dx10 web UI host (FastAPI + React build) on Windows.
REM Double-click this file, then open http://127.0.0.1:8000 in the browser.
REM (Chay 1 lan: pip install -r requirements.txt — quickstart.bat da lam.)
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Khong tim thay python. Chay quickstart.bat truoc de cai Python.
  pause
  exit /b 1
)
set PYTHONPATH=%~dp0src
python -m diamondx10.webapi %*
if errorlevel 1 (
  echo.
  echo Loi khi chay web UI. Kiem tra lai Python va requirements (pip install -r requirements.txt).
  pause
)
endlocal
