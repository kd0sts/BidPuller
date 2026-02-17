@echo off
setlocal

REM Build a Windows .exe for cash_bids_monitor.py using PyInstaller.
REM Run this from Command Prompt on Windows in the repo root.

python --version >NUL 2>&1
if errorlevel 1 (
  echo Python is required but was not found in PATH.
  exit /b 1
)

python -m pip install --upgrade pip pyinstaller
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist cash_bids_monitor.spec del /q cash_bids_monitor.spec

pyinstaller --onefile --name bidpuller cash_bids_monitor.py
if errorlevel 1 exit /b 1

echo.
echo Build complete: dist\bidpuller.exe
endlocal
