# =====================================================================
#  PROBE_MODELO.PS1 - raio-X de QUALQUER .blend, sem abrir o Blender
#  (chamado pelo probe_modelo.bat; pode rodar direto tambem)
#  Cada modelo gera util\model_probe_<nome>.json e pergunta se ja envia
#  pro repo (commit+push). Pode rodar varias vezes, um personagem por vez.
# =====================================================================
$ErrorActionPreference = "Continue"
$Repo   = Split-Path -Parent $PSScriptRoot
$Util   = $PSScriptRoot
$ProbePy = Join-Path $Repo "tools\model_probe.py"

Write-Host ""
Write-Host "  === BLOOM AGENT - RAIO-X DO MODELO ===" -ForegroundColor Cyan
Write-Host "  (vale para qualquer .blend: Hsin/WuWa ou personagens de outros jogos)"
Write-Host ""

# ---------- [1/4] achar o blender.exe ----------
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
    # Steam em qualquer disco: Steam\ ou SteamLibrary\ na raiz de cada drive
    foreach ($d in (Get-PSDrive -PSProvider FileSystem).Root) {
        foreach ($s in @("Steam","SteamLibrary")) {
            $c = Join-Path $d "$s\steamapps\common\Blender\blender.exe"
            if (Test-Path $c) { return $c }
        }
    }
    # bibliotecas Steam cadastradas (libraryfolders.vdf)
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

$Blender = Achar-Blender
if (-not $Blender) {
    Write-Host "  Nao achei o blender.exe nos lugares de sempre." -ForegroundColor Yellow
    Write-Host "  Cole o caminho da PASTA do Blender (ex.: D:\Steam\steamapps\common\Blender)"
    $pasta = Read-Host "  Caminho"
    if ($pasta -and (Test-Path (Join-Path $pasta "blender.exe"))) { $Blender = Join-Path $pasta "blender.exe" }
    elseif ($pasta -and (Test-Path $pasta)) { $Blender = $pasta }
}
if (-not $Blender -or -not (Test-Path $Blender)) {
    Write-Host "  [X] Blender nao encontrado. Me diga o caminho na conversa com o agent." -ForegroundColor Red
    exit 1
}
Write-Host "  [1/4] Blender: $Blender"

# ---------- [2/4] achar os .blend ----------
$raizes = @()
if (Test-Path "J:\3d-Create") { $raizes += "J:\3d-Create" }
foreach ($p in @("Desktop","Downloads","Documents")) {
    $q = Join-Path $env:USERPROFILE $p
    if (Test-Path $q) { $raizes += $q }
}
Write-Host "  [2/4] Procurando .blend..."
$candidatos = @()
foreach ($r in $raizes) {
    $candidatos += Get-ChildItem -Path $r -Recurse -Filter *.blend -File -ErrorAction SilentlyContinue
}
$candidatos = $candidatos | Sort-Object LastWriteTime -Descending | Select-Object -First 15

$Blend = $null
if ($candidatos.Count -gt 0) {
    $lista = for ($i = 0; $i -lt $candidatos.Count; $i++) {
        [pscustomobject]@{
            "N"        = ($i + 1)
            "Modificado" = $candidatos[$i].LastWriteTime.ToString("dd/MM/yyyy HH:mm")
            "MB"       = [math]::Round($candidatos[$i].Length / 1MB)
            "Caminho"  = $candidatos[$i].FullName
        }
    }
    Write-Host ""
    Write-Host "  Escolha o personagem do raio-X:" -ForegroundColor Cyan
    $esc = $null
    try { $esc = $lista | Out-GridView -Title "Raio-X: escolha o .blend" -OutputMode Single } catch { $esc = $null }
    if ($esc) { $Blend = $esc.Caminho }
    else {
        # menu numerado no proprio console
        $lista | Format-Table -AutoSize | Out-Host
        $n = Read-Host "  Numero do arquivo (Enter = colar caminho)"
        if ($n -match '^\d+$') {
            $achou = $lista | Where-Object { $_."N" -eq [int]$n }
            if ($achou) { $Blend = $achou.Caminho }
        }
    }
}
if (-not $Blend) {
    Write-Host "  Cole o caminho completo do .blend:"
    $Blend = Read-Host "  Caminho"
}
$Blend = $Blend.Trim('"').Trim()
if (-not ($Blend -and (Test-Path $Blend))) {
    Write-Host "  [X] Arquivo nao existe: $Blend" -ForegroundColor Red
    exit 1
}

$Nome = [System.IO.Path]::GetFileNameWithoutExtension($Blend)
$Nome = [regex]::Replace($Nome, "[^\w\-]", "_").Trim("_")
if (-not $Nome) { $Nome = "modelo" }
$Json = Join-Path $Util ("model_probe_{0}.json" -f $Nome)
Write-Host "        Modelo: $Blend"
Write-Host "        Relatorio: $Json"

# ---------- [3/4] rodar o raio-X ----------
Write-Host "  [3/4] Rodando o raio-X (sem abrir o Blender; pode levar ~1 min)..." -ForegroundColor Cyan
if (Test-Path $Json) { Remove-Item $Json -Force }
& $Blender --background --factory-startup $Blend --python $ProbePy -- --out $Json
if (-not (Test-Path $Json)) {
    Write-Host "  [X] O raio-X falhou. Me mande uma foto do erro acima na conversa." -ForegroundColor Red
    exit 1
}
Write-Host "        Salvo em: $Json" -ForegroundColor Green

# ---------- [4/4] commit + push ----------
Write-Host "  [4/4] Quer ja enviar o resultado pro repo? (o agent le na proxima rodada)"
$sync = Read-Host "  Enter = SIM / N = nao"
if ($sync -ne "N") {
    Push-Location $Repo
    $msg = "probe: model_probe_$Nome.json (raio-X para o agent)"
    $cli = $null
    foreach ($py in @("python","py -3")) {
        try {
            $arr = $py.Split(" ")
            if ($arr.Count -eq 1) { & $arr[0] "tools\project_cli.py" sync -m $msg }
            else { & $arr[0] "-3" "tools\project_cli.py" sync -m $msg }
            if ($LASTEXITCODE -eq 0) { $cli = $py; break }
        } catch { }
    }
    Pop-Location
    if ($cli) {
        Write-Host "  Pronto! Volte na conversa e diga: ""probe enviado: $Nome""" -ForegroundColor Green
    } else {
        Write-Host "  [!] Nao consegui sincronizar agora. Depois rode o DevKit.bat." -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "  Concluido. Para outro personagem, rode o .bat de novo." -ForegroundColor Cyan
