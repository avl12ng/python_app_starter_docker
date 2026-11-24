@echo off
rem ===========================================================================
rem  Installation / mise a jour de l'application (Windows, sans Docker)
rem  Prerequis : Python 3.12+ installe avec l'option "Add python.exe to PATH".
rem  A relancer apres chaque mise a jour du code (application arretee).
rem  Option : install.bat /nopause  (sans pause finale, pour un lancement automatique)
rem ===========================================================================
setlocal
cd /d "%~dp0.."
echo === Installation de l'application ===
echo Dossier : %CD%

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python 3.12 ou plus est introuvable dans le PATH.
    echo Installer Python depuis https://www.python.org/downloads/windows/
    echo en cochant "Add python.exe to PATH", puis rouvrir l'invite de commandes.
    goto :erreur
)
python --version

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement virtuel .venv ...
    python -m venv .venv || goto :erreur
)

echo Installation des dependances ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip || goto :erreur
".venv\Scripts\python.exe" -m pip install --quiet -e . || goto :erreur

".venv\Scripts\python.exe" -m app.cli init-env || goto :erreur

echo Migrations de la base ...
".venv\Scripts\python.exe" -m alembic upgrade head || goto :erreur

echo.
echo Installation terminee.
echo Lancer windows\start.bat puis ouvrir http://localhost:8095
if /i not "%~1"=="/nopause" pause
exit /b 0

:erreur
echo.
echo [ERREUR] L'installation a echoue : voir les messages ci-dessus.
if /i not "%~1"=="/nopause" pause
exit /b 1
