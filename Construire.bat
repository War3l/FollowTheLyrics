@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Installation de l'environnement...
  python -m venv .venv
)
".venv\Scripts\python.exe" -c "import followthelyrics" 2>nul || ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -e .
".venv\Scripts\python.exe" -m pip install --quiet pyinstaller
".venv\Scripts\python.exe" tools\build.py
pause
