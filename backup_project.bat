@echo off
rem Copy of the project as one file: git bundle with full history + verify. Run from the project root: backup_project.bat E:\backup
if "%~1"=="" (echo Usage: backup_project.bat E:\backup & exit /b 1)
if not exist "%~1" mkdir "%~1"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set D=%%i
git bundle create "%~1\project-%D%.bundle" --all && git bundle verify "%~1\project-%D%.bundle" && echo Done: %~1\project-%D%.bundle. Third copy: git push -u origin BRANCH to the remote repository.
