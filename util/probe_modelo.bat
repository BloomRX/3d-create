@echo off
setlocal EnableExtensions
title Bloom Agent - Raio-X do modelo (.blend)

rem ====================================================================
rem  PROBE_MODELO.BAT - raio-X do .blend sem abrir o Blender
rem  Uso: dois cliques aqui. Ou arraste um .blend em cima deste arquivo.
rem  Salva util\model_probe.json e pergunta se ja envia (commit+push).
rem ====================================================================

set "REPO=%~dp0.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
set "PROBE_JSON=%REPO%\util\model_probe.json"

echo.
echo   === BLOOM AGENT - RAIO-X DO MODELO ===
echo.

rem ---- [1/4] achar o blender.exe ----
set "BLENDER="
for %%V in (5.2 5.1 5.0 4.5 4.2) do if not defined BLENDER if exist "%ProgramFiles%\Blender Foundation\Blender %%V\blender.exe" set "BLENDER=%ProgramFiles%\Blender Foundation\Blender %%V\blender.exe"
if not defined BLENDER for /f "delims=" %%F in ('where blender 2^>nul') do if not defined BLENDER set "BLENDER=%%F"
if not defined BLENDER (
    echo   [X] Blender nao encontrado em "C:\Program Files\Blender Foundation".
    echo       Instale o Blender ou me diga o caminho na conversa com o agent.
    goto :fim_erro
)
echo   [1/4] Blender: %BLENDER%

rem ---- [2/4] achar o .blend ----
set "BLEND=%~1"
if defined BLEND goto :tem_blend
echo   [2/4] Procurando .blend (banco J:\3d-Create, Desktop, Downloads, Documentos)...
set "TMP_LIST=%TEMP%\bloom_probe_blend.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$raizes=@(); if (Test-Path 'J:\3d-Create') { $raizes += 'J:\3d-Create' }; foreach ($p in @('Desktop','Downloads','Documents')) { $q = Join-Path $env:USERPROFILE $p; if (Test-Path $q) { $raizes += $q } }; Get-ChildItem -Path $raizes -Recurse -Filter *.blend -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 8 -ExpandProperty FullName" > "%TMP_LIST%" 2>nul
set /a N=0
for /f "usebackq delims=" %%F in ("%TMP_LIST%") do set /a N+=1
if "%N%"=="0" (
    echo   Nenhum .blend encontrado nos lugares de sempre.
    goto :perguntar_caminho
)
if "%N%"=="1" (
    for /f "usebackq delims=" %%F in ("%TMP_LIST%") do set "BLEND=%%F"
    goto :tem_blend
)
echo   Achei %N% .blend (do mais recente pro mais antigo^):
set /a I=0
for /f "usebackq delims=" %%F in ("%TMP_LIST%") do (
    set /a I+=1
    call echo     %%I%%. %%F
)
echo   Se algum desses e o modelo, copie o caminho dele aqui embaixo.
echo   (Ou simplesmente ARRASTE o .blend pra dentro desta janela.^)

:perguntar_caminho
set "BLEND="
set /p "BLEND=   Caminho do .blend: "
if not defined BLEND (
    echo   [X] Nenhum caminho informado.
    goto :fim_erro
)
set "BLEND=%BLEND:"=%"

:tem_blend
if not exist "%BLEND%" (
    echo   [X] Arquivo nao existe: %BLEND%
    goto :fim_erro
)
echo         Modelo: %BLEND%

rem ---- [3/4] rodar o raio-X ----
echo   [3/4] Rodando o raio-X (sem abrir o Blender; pode levar ~1 min^)...
if exist "%PROBE_JSON%" del "%PROBE_JSON%"
"%BLENDER%" --background --factory-startup "%BLEND%" --python "%REPO%\tools\model_probe.py" -- --out "%PROBE_JSON%"
if not exist "%PROBE_JSON%" (
    echo   [X] O raio-X falhou. Rode de novo e me mande uma foto do erro,
    echo       ou cole aqui o que apareceu acima.
    goto :fim_erro
)
echo         Salvo em: %PROBE_JSON%
echo         (o resumo apareceu acima em "=== MODEL PROBE ===")

rem ---- [4/4] commit + push ----
echo   [4/4] Quer ja enviar o resultado pro repo? (o agent le na proxima rodada^)
set "SYNC=S"
set /p "SYNC=   Enter = SIM / N = nao: "
if /i "%SYNC%"=="N" goto :fim_ok
cd /d "%REPO%"
where python >nul 2>nul
if not errorlevel 1 (
    python tools\project_cli.py sync -m "probe: model_probe.json do .blend (raio-X para o agent)"
    goto :sync_feito
)
py -3 tools\project_cli.py sync -m "probe: model_probe.json do .blend (raio-X para o agent)"

:sync_feito
if errorlevel 1 (
    echo   [!] Nao consegui dar commit+push agora (sem internet?^).
    echo       Depois rode o DevKit.bat pra sincronizar.
    goto :fim_ok
)
echo   Pronto! Avisou la na conversa: "probe enviado".
goto :fim_ok

:fim_ok
echo.
echo   Concluido.
pause
exit /b 0

:fim_erro
echo.
pause
exit /b 1
