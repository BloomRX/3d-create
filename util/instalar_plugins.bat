@echo off
rem Instalador de plugins - a logica vive no instalar_plugins.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_plugins.ps1"
echo.
pause
