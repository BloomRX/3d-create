@echo off
chcp 65001 >nul
echo ================================================
echo  Limpador de instalacoes do Bloom Agent
echo  FECHE O BLENDER ANTES DE CONTINUAR (importante)
echo ================================================
echo.
for /d %%V in ("%APPDATA%\Blender Foundation\Blender\*") do (
  echo Limpando Blender %%~nxV ...
  if exist "%%V\scripts\addons\bloom_agent" rmdir /s /q "%%V\scripts\addons\bloom_agent"
  if exist "%%V\extensions\user_default\bloom_agent" rmdir /s /q "%%V\extensions\user_default\bloom_agent"
)
echo.
echo Pronto! Agora: abra o Blender ^> Preferences ^> Add-ons ^> Install
echo e escolha o bloom_agent_addon.zip (gerado pelo zip_addon.bat).
echo.
pause
