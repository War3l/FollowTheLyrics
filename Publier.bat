@echo off
chcp 65001 >nul
cd /d "%~dp0"
set /p CUR=<src\followthelyrics\VERSION
echo Version actuelle : %CUR%
set /p V=Nouvelle version (exemple 1.1.0) : 
if "%V%"=="" goto :fin
set /p NOTES=Quoi de neuf (une phrase) : 
if "%NOTES%"=="" set NOTES=Mise a jour %V%

>src\followthelyrics\VERSION echo %V%
".venv\Scripts\python.exe" tools\build.py
if errorlevel 1 goto :echec
if not exist "dist\FollowTheLyrics.exe" goto :echec

git add -A
git commit -m "Version %V% : %NOTES%"
git push
if errorlevel 1 goto :echec
gh release create v%V% "dist\FollowTheLyrics.exe" --title "FollowTheLyrics %V%" --notes "%NOTES%"
if errorlevel 1 goto :echec
echo.
echo Publie : la version %V% est en ligne.
goto :fin

:echec
echo.
echo Quelque chose a echoue : rien d'autre n'a ete publie. Lis le message au-dessus.
:fin
pause
