@echo off
rem ===========================================================================
rem  Demarre l'application. Reglages (port, HTTPS, nom...) : fichier .env
rem  Arret : Ctrl+C, ou fermer la fenetre.
rem  Option : start.bat /nopause  (demarrage automatique par le Planificateur de taches)
rem ===========================================================================
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Lancer d'abord windows\install.bat
    goto :fin
)

rem Applique les migrations eventuelles puis lance le serveur web
".venv\Scripts\python.exe" -m app.serve

:fin
if /i not "%~1"=="/nopause" pause
