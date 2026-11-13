@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Premiere installation, ca prend une minute...
  python -m venv .venv
)
".venv\Scripts\python.exe" -c "import followthelyrics" 2>nul || ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -e .
start "" ".venv\Scripts\pythonw.exe" -m followthelyrics %*
