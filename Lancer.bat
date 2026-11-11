@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Premiere installation, ca prend une minute...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
)
start "" ".venv\Scripts\pythonw.exe" overlay.py %*
