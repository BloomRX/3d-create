@echo off
setlocal EnableExtensions
title Bloom Agent - Raio-X do modelo (.blend)

rem ====================================================================
rem  PROBE_MODELO.BAT - raio-X de QUALQUER .blend, sem abrir o Blender
rem  Dois cliques; escolha o personagem no menu (ou arraste o arquivo).
rem  Cada modelo gera util\model_probe_<nome>.json e ele pergunta se ja
rem  envia pro repo (commit+push) - pode rodar varias vezes.
rem ====================================================================

set "REPO=%~dp0.."
for %%I in ("%REPO%") do set "REPO=%%~fI"

echo.
echo   === BLOOM AGENT - RAIO-X DO MODELO ===
echo   (vale para qualquer .blend: Hsin/WuWa ou personagens de outros jogos)
echo.

rem ---- [1/4] achar o blender.exe (PATH, Program Files ou Steam) ----
set "BLENDER="
for %%V in (5.2 5.1 5.0 4.5 4.2) do if not defined BLENDER if exist "%ProgramFiles%\Blender Foundation\Blender %%V\blender.exe" set "BLENDER=%ProgramFiles%\Blender Foundation\Blender %%V\blender.exe"
if not defined BLENDER for %%D in (C D E F G) do (
    if not defined BLENDER if exist "%%D:\Steam\steamapps\common\Blender\blender.exe" set "BLENDER=%%D:\Steam\steamapps\common\Blender\blender.exe"
    if not defined BLENDER if exist "%%D:\SteamLibrary\steamapps\common\Blender\blender.exe" set "BLENDER=%%D:\SteamLibrary\steamapps\common\Blender\blender.exe"
)
if not defined BLENDER if exist "%ProgramFiles(x86)%\Steam\steamapps\common\Blender\blender.exe" set "BLENDER=%ProgramFiles(x86)%\Steam\steamapps\common\Blender\blender.exe"
if not defined BLENDER (
    rem bibliotecas Steam em outros discos (libraryfolders.vdf)
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$vf = Join-Path ${env:ProgramFiles(x86)} 'Steam\steamapps\libraryfolders.vdf'; if (Test-Path $vf) { Select-String -Path $vf -Pattern 'path' | ForEach-Object { $p = ($_.Line -split '\"')[1] -replace '\\\\', '\'; $c = Join-Path $p 'steamapps\common\Blender\blender.exe'; if (Test-Path $c) { Write-Output $c } } | Select-Object -First 1 }" > "%TEMP%\bloom_blender.txt" 2>nul
    for /f "usebackq delims=" %%F in ("%TEMP%\bloom_blender.txt") do if not defined BLENDER set "BLENDER=%%F"
)
if not defined BLENDER for /f "delims=" %%F in ('where blender 2^>nul') do if not defined BLENDER set "BLENDER=%%F"
if not defined BLENDER (
    echo   Nao achei o blender.exe nos lugares de sempre.
    echo   Cole o caminho da PASTA do Blender e aperte Enter.
    echo   Exemplo Steam: D:\Steam\steamapps\common\Blender
    set "BLENDER="
    set /p "BLENDER=   Caminho: "
    if not defined BLENDER goto :fim_erro
    set "BLENDER=%BLENDER:"=%"
    if exist "%BLENDER%\blender.exe" set "BLENDER=%BLENDER%\blender.exe"
)
if not exist "%BLENDER%" (
    echo   [X] Nao encontrei: %BLENDER%
    goto :fim_erro
)
echo   [1/4] Blender: %BLENDER%

rem ---- [2/4] listar os .blend disponiveis ----
echo   [2/4] Procurando .blend no banco J:\3d-Create e nas pastas de usuario...
set "TMP_LIST=%TEMP%\bloom_probe_blend.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$raizes=@(); if (Test-Path 'J:\3d-Create') { $raizes += 'J:\3d-Create' }; foreach ($p in @('Desktop','Downloads','Documents')) { $q = Join-Path $env:USERPROFILE $p; if (Test-Path $q) { $raizes += $q } }; Get-ChildItem -Path $raizes -Recurse -Filter *.blend -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 15 -ExpandProperty FullName" > "%TMP_LIST%" 2>nul
set /a N=0
for /f "usebackq delims=" %%F in ("%TMP_LIST%") do set /a N+=1
if "%N%"=="0" (
    echo   Nenhum .blend encontrado nos lugares de sempre.
    goto :perguntar_caminho
)

rem ---- menu de escolha ----
setlocal EnableDelayedExpansion
echo.
echo   Achei %N% .blend (mais recente primeiro^). Qual personagem vai ser o raio-X?
echo.
set /a I=0
for /f "usebackq delims=" %%F in ("%TMP_LIST%") do (
    set /a I+=1
    set "CAND_!I!=%%F"
    set "SZ=%%~zF"
    set /a MB=SZ/1048576
    echo     !I!.  [%%~tF]  !MB! MB   %%F
)
echo.
set "ESCOLHA="
set /p "ESCOLHA=   Numero do arquivo (1-%N%; Enter = colar caminho; 0 = sair): "
if "%ESCOLHA%"=="0" exit /b 0
set "BLEND=!CAND_%ESCOLHA%!"
endlocal & set "BLEND=%BLEND%"
if not defined BLEND (
    echo   Opcao invalida.
    goto :perguntar_caminho
)
goto :tem_blend

:perguntar_caminho
echo   Cole o caminho completo do .blend (ou ARRASTE o arquivo pra ca dentro^):
set "BLEND="
set /p "BLEND=   Caminho: "
if not defined BLEND (
    echo   [X] Nenhum caminho informado.
    goto :fim_erro
)

:tem_blend
set "BLEND=%BLEND:"=%"
if not exist "%BLEND%" (
    echo   [X] Arquivo nao existe: %BLEND%
    goto :fim_erro
)
for %%N in ("%BLEND%") do set "NOME=%%~nN"
set "NOME=%NOME: =_%"
set "NOME=%NOME:(=%"
set "NOME=%NOME:)=%"
set "NOME=%NOME:,=%"
set "NOME=%NOME:&=e%"
set "NOME=%NOME:'=%"
if not defined NOME set "NOME=modelo"
set "PROBE_JSON=%REPO%\util\model_probe_%NOME%.json"
echo         Modelo: %BLEND%
echo         Relatorio: %PROBE_JSON%

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
echo         (o resumo apareceu acima em "=== MODEL PROBE ==="^)

rem ---- [4/4] commit + push ----
echo   [4/4] Quer ja enviar o resultado pro repo? (o agent le na proxima rodada^)
set "SYNC=S"
set /p "SYNC=   Enter = SIM / N = nao: "
if /i "%SYNC%"=="N" goto :fim_ok
cd /d "%REPO%"
set "MSG=probe: model_probe_%NOME%.json (raio-X para o agent)"
where python >nul 2>nul
if not errorlevel 1 (
    python tools\project_cli.py sync -m "%MSG%"
    goto :sync_feito
)
py -3 tools\project_cli.py sync -m "%MSG%"

:sync_feito
if errorlevel 1 (
    echo   [!] Nao consegui dar commit+push agora (sem internet?^).
    echo       Depois rode o DevKit.bat pra sincronizar.
    goto :fim_ok
)
echo   Pronto! Volte na conversa e diga: "probe enviado: %NOME%".
echo   Para outro personagem, rode este .bat de novo - cada um gera o seu JSON.
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
