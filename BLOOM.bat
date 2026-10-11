@echo off
rem ================================================================
rem  BLOOM.BAT - A UNICA ROTINA DO PROJETO (dah dois cliques aqui)
rem  pull + plugins + raio-X + CI + commit/push + abrir Blender
rem ================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0util\bloom.ps1"
echo.
pause
