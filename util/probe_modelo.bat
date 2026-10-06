@echo off
rem Lancador do raio-X de modelos - a logica vive no probe_modelo.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0probe_modelo.ps1"
echo.
pause
