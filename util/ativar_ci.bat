@echo off
rem ============================================================
rem  ATIVAR_CI.BAT - liga o GitHub Actions (testes a cada push)
rem  Rode UMA vez depois de um git pull. Precisa de git + python.
rem ============================================================
cd /d "%~dp0.."
if exist ".github\workflows\tests.yml" (
    echo O CI ja esta ativo. Nada a fazer.
    pause
    exit /b 0
)
if not exist "tools\ci\tests.yml" (
    echo Arquivo tools\ci\tests.yml nao encontrado.
    echo Rode git pull primeiro e rode este arquivo de novo.
    pause
    exit /b 1
)
if not exist ".github\workflows" mkdir ".github\workflows"
git mv "tools/ci/tests.yml" ".github/workflows/tests.yml"
if errorlevel 1 (
    echo Falhou o git mv. Me mande um print desta janela na conversa.
    pause
    exit /b 1
)
where python >nul 2>nul
if not errorlevel 1 (
    python tools\project_cli.py sync -m "ci: ativa GitHub Actions - testes automaticos em todo push"
    goto :fim
)
py -3 tools\project_cli.py sync -m "ci: ativa GitHub Actions - testes automaticos em todo push"
:fim
echo.
echo Se o sync terminou com "Sincronizacao concluida", o CI esta ativo!
echo A partir do proximo push, veja o resultado na aba Actions do GitHub.
pause
