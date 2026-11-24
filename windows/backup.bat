@echo off
rem ===========================================================================
rem  Sauvegarde a chaud de la base SQLite : backups\app-AAAA-MM-JJ_HHMM.db
rem  L'application peut rester demarree. Supprime les sauvegardes de plus de KEEP_DAYS jours.
rem  A planifier chaque nuit, puis copier le dossier backups hors du serveur.
rem ===========================================================================
setlocal
cd /d "%~dp0.."
set KEEP_DAYS=30

".venv\Scripts\python.exe" -m app.cli backup
if errorlevel 1 (
    echo [ERREUR] La sauvegarde a echoue.
    exit /b 1
)

forfiles /p backups /m app-*.db /d -%KEEP_DAYS% /c "cmd /c del @path" >nul 2>&1
exit /b 0
