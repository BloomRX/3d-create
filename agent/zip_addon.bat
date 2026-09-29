@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m zipfile -c bloom_agent_addon.zip bloom_agent
) else (
    python -m zipfile -c bloom_agent_addon.zip bloom_agent
)
if errorlevel 1 (
    echo ERRO ao gerar o zip.
    exit /b 1
)
echo.
echo Addon gerado: %~dp0bloom_agent_addon.zip
echo No Blender: Edit ^> Preferences ^> Add-ons ^> Install... ^> selecione o zip ^> habilitar "Bloom Agent".
if "%~1"=="" pause
exit /b 0
