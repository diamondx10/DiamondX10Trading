@echo off
REM ==========================================================================
REM DiamondX10 quickstart.bat — diem vao duy nhat tren Windows.
REM
REM Khong can Python hay pip san: file nay tu tim Python 3.10+, neu chua
REM co thi tu cai Python (qua winget; neu khong co winget thi tai bo cai
REM chinh thuc tu python.org va cai lang, khong can quyen admin), roi
REM chay quickstart.py — quickstart.py se tu cai cac goi can thiet
REM (requirements.txt + MetaTrader5) va kiem tra MT5 terminal truoc khi
REM hoi thong tin dang nhap.
REM
REM Cach dung: nhap doi vao file nay, hoac tu cmd/PowerShell:
REM   quickstart.bat
REM   quickstart.bat --check-only
REM   quickstart.bat --live-once
REM   quickstart.bat --live
REM   quickstart.bat --trade
REM ==========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM --- Luu PYTHONPATH vinh vien (setx) de lenh "python -m diamondx10 ..."
REM chay duoc o bat ky cua so moi nao ma khong can go $env:PYTHONPATH nua.
REM "set" chi co tac dung trong phien bat nay; "setx" ghi vao registry
REM (chi ap dung cho cua so mo SAU khi chay file nay).
set "PYTHONPATH=%~dp0src"
setx PYTHONPATH "%~dp0src" >nul 2>nul
if %errorlevel%==0 (
  echo [quickstart.bat] Da luu PYTHONPATH (setx) cho cac lan chay sau.
) else (
  echo [quickstart.bat] Khong luu duoc PYTHONPATH (setx) — van chay duoc trong lan nay.
)

set "PY="
set "PY_VERSION=3.12.10"
set "PY_INSTALLER_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"

call :FIND_PYTHON
if defined PY goto :HAVE_PY

echo [quickstart.bat] Khong tim thay Python 3.10+ tren may nay.
echo [quickstart.bat] Dang thu cai Python %PY_VERSION% ...

REM --- Cach 1: winget (Windows 10/11, lay ban 3.12 moi nhat) ---
where winget >nul 2>nul
if %errorlevel%==0 (
  echo [quickstart.bat] Cai Python qua winget ...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
  call :FIND_PYTHON
  if defined PY goto :HAVE_PY
  echo [quickstart.bat] Cai qua winget khong xong, thu cach tai truc tiep ...
) else (
  echo [quickstart.bat] May nay khong co winget, thu cach tai truc tiep ...
)

REM --- Cach 2: tai bo cai chinh thuc tu python.org ---
echo [quickstart.bat] Tai bo cai Python tu python.org ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%PY_INSTALLER_URL%' -OutFile \"$env:TEMP\python-installer.exe\" -UseBasicParsing; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
  echo [quickstart.bat] LOI: khong tai duoc bo cai Python. Kiem tra mang roi chay lai.
  echo [quickstart.bat] Hoac cai tay Python 3.10+ tai https://www.python.org/downloads/ roi chay lai file nay.
  exit /b 1
)
echo [quickstart.bat] Cai Python (lang, khong can quyen admin) ...
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%TEMP%\python-installer.exe" >nul 2>nul
call :FIND_PYTHON
if not defined PY (
  echo [quickstart.bat] LOI: cai xong nhung van khong tim thay python.exe.
  echo [quickstart.bat] Hay dong cua so cmd nay, mo cua so moi roi chay lai file nay.
  echo [quickstart.bat] Neu van loi, cai tay Python 3.10+ tai https://www.python.org/downloads/
  exit /b 1
)

:HAVE_PY
echo [quickstart.bat] Dung Python: %PY%
"%PY%" quickstart.py %*
exit /b %errorlevel%

REM --------------------------------------------------------------------------
REM :FIND_PYTHON — tim Python 3.10+ hop le, dat vao bien PY (rong neu khong co).
REM Thu theo thu tu: py launcher, python, python3, roi duong dan cai mac dinh.
REM --------------------------------------------------------------------------
:FIND_PYTHON
set "PY="
for %%C in (py python python3) do (
  if not defined PY (
    where %%C >nul 2>nul
    if !errorlevel!==0 (
      %%C -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
      if !errorlevel!==0 set "PY=%%C"
    )
  )
)
if defined PY exit /b 0
for %%V in (312 311 310) do (
  if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    if not defined PY if exist "%ProgramFiles%\Python%%V\python.exe" set "PY=%ProgramFiles%\Python%%V\python.exe"
  )
)
exit /b 0
