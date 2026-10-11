# Instalador de plugins do repo no Blender (todos ficam DESLIGADOS).
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot

function Achar-Blender {
    $cmd = Get-Command blender.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($pf in @(${env:ProgramFiles}, ${env:ProgramFiles(x86)})) {
        if (-not $pf) { continue }
        foreach ($v in @("5.2","5.1","5.0","4.5","4.2")) {
            $c = Join-Path $pf "Blender Foundation\Blender $v\blender.exe"
            if (Test-Path $c) { return $c }
        }
    }
    foreach ($d in (Get-PSDrive -PSProvider FileSystem).Root) {
        foreach ($s in @("Steam","SteamLibrary")) {
            $c = Join-Path $d "$s\steamapps\common\Blender\blender.exe"
            if (Test-Path $c) { return $c }
        }
    }
    foreach ($pf in @(${env:ProgramFiles}, ${env:ProgramFiles(x86)})) {
        $vdf = Join-Path $pf "Steam\steamapps\libraryfolders.vdf"
        if (-not (Test-Path $vdf)) { continue }
        foreach ($linha in (Get-Content $vdf)) {
            $tokens = @($linha -split [string][char]34)
            foreach ($ix in @(1, 3)) {
                if ($tokens.Count -le $ix) { continue }
                $pedaco = $tokens[$ix]
                if (-not $pedaco -or $pedaco -eq "path") { continue }
                $c = Join-Path ($pedaco -replace "\\\\", "\") "steamapps\common\Blender\blender.exe"
                if (Test-Path $c) { return $c }
            }
        }
    }
    return $null
}

Write-Host ""
Write-Host "  === BLOOM AGENT - INSTALAR PLUGINS ===" -ForegroundColor Cyan
Write-Host "  (instala os zips do repo; todos ficam DESLIGADOS por padrao)"
Write-Host ""

$Blender = Achar-Blender
if (-not $Blender) {
    Write-Host "  Nao achei o blender.exe. Cole o caminho da PASTA do Blender:"
    $pasta = Read-Host "  Caminho"
    if ($pasta -and (Test-Path (Join-Path $pasta "blender.exe"))) { $Blender = Join-Path $pasta "blender.exe" }
}
if (-not $Blender -or -not (Test-Path $Blender)) {
    Write-Host "  [X] Blender nao encontrado." -ForegroundColor Red
    exit 1
}
Write-Host "  Blender: $Blender"

$total = 0
foreach ($p in @((Join-Path $Repo "plugins_src"), (Join-Path $Repo "assets\learn"))) {
    if (Test-Path $p) { $total += (Get-ChildItem $p -Filter *.zip -File -ErrorAction SilentlyContinue).Count }
}
if ($total -eq 0) {
    Write-Host "  [X] Nenhum .zip encontrado em plugins_src\ nem assets\learn\." -ForegroundColor Yellow
    exit 1
}
Write-Host "  Instalando $total plugin(s)... (fecha o Blender antes se estiver aberto)"
& $Blender --background --python (Join-Path $PSScriptRoot "instalar_plugins.py")
Write-Host ""
Write-Host "  Pronto! Os plugins estao INSTALADOS mas DESLIGADOS." -ForegroundColor Green
Write-Host "  Ligar quando o agent pedir: Edit > Preferences > Add-ons"
