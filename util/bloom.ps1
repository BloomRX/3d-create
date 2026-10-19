# =====================================================================
#  BLOOM - rotina unica do projeto (o unico .bat que voce precisa)
#  1. limpa temporarios   2. pull   3. instala plugins novos (desligados)
#  4. raio-X de modelos .blend/.vrm novos   5. ativa CI (1a vez)
#  6. commit+push do que surgir   7. pergunta se quer abrir o Blender
# =====================================================================
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = Join-Path $Logs ("bloom_{0:yyyy-MM-dd_HHmmss}.txt" -f (Get-Date))
Start-Transcript -Path $Log | Out-Null

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

function Achar-Python {
    foreach ($py in @("python", "py")) { if (Get-Command $py -ErrorAction SilentlyContinue) { return $py } }
    return $null
}

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Cyan
Write-Host "   BLOOM AGENT - ROTINA COMPLETA" -ForegroundColor Cyan
Write-Host "  ==========================================" -ForegroundColor Cyan
$HashAntes = (Get-FileHash $PSCommandPath -Algorithm MD5).Hash

# ---------- [1/6] limpar temporarios ----------
Get-ChildItem $env:TEMP -Filter "bloom_*" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "  [1/7] Temporarios limpos."

# ---------- [2/6] pull ----------
$py = Achar-Python
Write-Host "  [2/7] Atualizando do repo (pull)..."
if ($py) {
    Push-Location $Repo
    & $py "tools\project_cli.py" pull 2>&1 | ForEach-Object { Write-Host "        $_" }
    Pop-Location
    # a rotina atualizou a si mesma? entao reinicia limpo com a versao nova
    $HashDepois = (Get-FileHash $PSCommandPath -Algorithm MD5).Hash
    if ($HashDepois -ne $HashAntes) {
        Write-Host "        (a rotina se atualizou — reiniciando com a versao nova...)" -ForegroundColor Yellow
        try { Stop-Transcript | Out-Null } catch { }
        & powershell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
        exit $LASTEXITCODE
    }
} else {
    Write-Host "        [!] Python nao encontrado; pulei o pull (rode git pull manual)." -ForegroundColor Yellow
}

# ---------- [3/7] addon Bloom Agent: versao instalada -> versao do repo ----------
if (-not $Blender) { $Blender = Achar-Blender }
Write-Host "  [3/7] Addon Bloom Agent..."
function Versao-Manifesto($caminho) {
    if (Test-Path $caminho) {
        foreach ($l in (Get-Content $caminho -ErrorAction SilentlyContinue)) {
            if ($l -match '^\s*version\s*=\s*"(\d+\.\d+\.\d+)"') { return $Matches[1] }
        }
    }
    return $null
}
$RepoAddon = Join-Path $Repo "agent\bloom_agent"
$VRepo = Versao-Manifesto (Join-Path $RepoAddon "blender_manifest.toml")
$VInst = $null
foreach ($bv in @("5.2","5.1","5.0","4.5","4.2")) {
    $cand = Join-Path $env:APPDATA "Blender Foundation\Blender\$bv\extensions\user_default\bloom_agent\blender_manifest.toml"
    $v = Versao-Manifesto $cand
    if ($v) { $VInst = $v; $InstDir = Split-Path -Parent $cand; break }
}
$VInstTxt = if ($VInst) { $VInst } else { "nenhum" }
$VRepoTxt = if ($VRepo) { $VRepo } else { "?" }
Write-Host "        instalado: $VInstTxt  |  repo: $VRepoTxt"
$ZipAddon = Join-Path $Repo "agent\bloom_agent_addon.zip"
if ($py) {
    Push-Location (Join-Path $Repo "agent")
    & $py -m zipfile -c $ZipAddon "bloom_agent"
    Pop-Location
    if (-not (Test-Path $ZipAddon) -or ((Get-Item $ZipAddon -ErrorAction SilentlyContinue).Length -lt 2048)) {
        Write-Host "        zip do addon ficou oco — refazendo com Compress-Archive..."
        Compress-Archive -Path (Join-Path $RepoAddon "*") -DestinationPath $ZipAddon -Force
    }
}
if ($Blender -and (Test-Path $ZipAddon) -and ($VRepo -ne $VInst)) {
    if ($VInst -and $InstDir -and (Test-Path $InstDir)) {
        Remove-Item $InstDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "        versao velha ($VInst) removida."
    }
    & $Blender --background --python (Join-Path $Repo "util\instalar_addon.py") -- --zip $ZipAddon 2>&1 |
        Where-Object { $_ -match "addon|ADDON|ligado|salvas|\[X\]|\[!\]" } |
        ForEach-Object { Write-Host "        $_" }
    $VConf = $null
    foreach ($bv in @("5.2","5.1","5.0","4.5","4.2")) {
        $v = Versao-Manifesto (Join-Path $env:APPDATA "Blender Foundation\Blender\$bv\extensions\user_default\bloom_agent\blender_manifest.toml")
        if (-not $v) { $v = Versao-Manifesto (Join-Path $env:APPDATA "Blender Foundation\Blender\$bv\scripts\addons\bloom_agent\blender_manifest.toml") }
        if ($v) { $VConf = $v; break }
    }
    if ($VConf -eq $VRepo) {
        foreach ($bv2 in @("5.2","5.1","5.0","4.5","4.2")) {
            foreach ($lixo in @("bloom_agent","mmd_tools","wiggle_bones")) {
                $lixoDir = Join-Path $env:APPDATA "Blender Foundation\Blender\$bv2\scripts\addons\$lixo"
                if (Test-Path $lixoDir) {
                    Remove-Item $lixoDir -Recurse -Force -ErrorAction SilentlyContinue
                    Write-Host "        lixo legado removido: scripts\addons\$bv2\$lixo (extensao agora mora em extensions)"
                }
            }
        }
        Write-Host "        CONFIRMADO: addon $VConf instalado (feche e reabra o Blender p/ carregar)." -ForegroundColor Green
    } else {
        $VConfTxt = if ($VConf) { $VConf } else { "nada" }
        Write-Host "        [X] deveria ser $VRepo e ficou '$VConfTxt'. Me avise na conversa com um print." -ForegroundColor Red
    }
} elseif ($VRepo -eq $VInst) {
    Write-Host "        ja esta na versao $VInst — nada a fazer."
} else {
    Write-Host "        [!] sem Blender/zip; atualize o addon manualmente (agent\zip_addon.bat)." -ForegroundColor Yellow
}

# ---------- [4/7] plugins ----------
$Blender = Achar-Blender
if (-not $Blender) {
    Write-Host "  Nao achei o blender.exe. Cole o caminho da PASTA do Blender:"
    Write-Host "  (exemplo Steam: D:\Steam\steamapps\common\Blender)"
    $pasta = Read-Host "  Caminho"
    if ($pasta -and (Test-Path (Join-Path $pasta "blender.exe"))) { $Blender = Join-Path $pasta "blender.exe" }
}
if (-not $Blender -or -not (Test-Path $Blender)) {
    Write-Host "  [4/7] Sem Blender; pulei a instalacao de plugins." -ForegroundColor Yellow
} else {
    Write-Host "  [4/7] Plugins (instala os novos; todos ficam DESLIGADOS)..."
    & $Blender --background --python (Join-Path $Repo "util\instalar_plugins.py") 2>&1 |
        Where-Object { $_ -match "plugin|RESUMO|pulados|AVISO|salvas" } |
        ForEach-Object { Write-Host "        $_" }
}

# ---------- [4/6] raio-X de modelos novos ----------
$Probes = Join-Path $Repo "probes"
New-Item -ItemType Directory -Force -Path $Probes | Out-Null
$raizes = @()
if (Test-Path "J:\3d-Create") { $raizes += "J:\3d-Create" }
foreach ($p in @("Desktop","Downloads","Documents")) {
    $q = Join-Path $env:USERPROFILE $p
    if (Test-Path $q) { $raizes += $q }
}
$modelos = @()
foreach ($r in $raizes) {
    $modelos += Get-ChildItem -Path $r -Recurse -Include *.blend,*.vrm -File -ErrorAction SilentlyContinue
}
$temVrmZip = @(Get-ChildItem (Join-Path $Repo "plugins") -Filter "*vrm*.zip" -File -ErrorAction SilentlyContinue).Count -gt 0
$faltando = @()
$vrmEsperando = 0
foreach ($m in ($modelos | Sort-Object LastWriteTime -Descending)) {
    $nome = [regex]::Replace([System.IO.Path]::GetFileNameWithoutExtension($m.Name), "[^\w\-]", "_").Trim("_")
    if (-not $nome) { $nome = "modelo" }
    if (Test-Path (Join-Path $Probes ("model_probe_{0}.json" -f $nome))) { continue }
    if ($m.Extension -ieq ".vrm" -and -not $temVrmZip) { $vrmEsperando += 1; continue }
    $faltando += $m
}
# ---------- [4.5] assets do catalogo (so CC0/CC-BY baixam sozinhos) ----------
Write-Host "  [4.5] Assets do catalogo..."
$CatFile = Join-Path $Repo "plugins\asset_catalog.json"
if (Test-Path $CatFile) {
    try {
        $Cat = ConvertFrom-Json (Get-Content $CatFile -Raw -Encoding UTF8)
        foreach ($item in $Cat.assets) {
            if (-not $item.url) { continue }
            $lic = [string]$item.licenca
            if ($lic -ne "CC0" -and $lic -ne "CC-BY") { continue }
            $dest = Join-Path $Repo ([string]$item.destino)
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            $nomeArq = ([string]$item.url) -replace "^/.*/", ""
            $nomeArq = ($nomeArq -split "\?")[0]
            if (-not $nomeArq) { $nomeArq = "$($item.id).zip" }
            $alvo = Join-Path $dest $nomeArq
            if (Test-Path $alvo) { continue }
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                Invoke-WebRequest -Uri ([string]$item.url) -OutFile $alvo -UseBasicParsing
                Write-Host "        baixado: $($item.id) ($lic)"
                if ($alvo -like "*.zip") {
                    Expand-Archive -Path $alvo -DestinationPath $dest -Force
                }
                $cred = Join-Path $Repo "assets\bank\CREDITS.md"
                Add-Content -Path $cred -Encoding UTF8 -Value "- $($item.id) | $lic | $($item.pagina) | $(Get-Date -Format yyyy-MM-dd)"
            } catch {
                Write-Host "        [!] falhou baixar $($item.id) — segue o baile" -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "        [!] catalogo com problema (ignorado): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host "  [5/7] Raio-X: $($faltando.Count) modelo(s) novo(s) sem relatorio."
if ($vrmEsperando -gt 0) {
    Write-Host "        $vrmEsperando arquivo(s) .vrm aguardando o VRM ADDON:" -ForegroundColor Yellow
    Write-Host "        1. Baixe o zip em github.com/saturday06/VRM_ADDON_FOR_BLENDER (Releases)"
    Write-Host "        2. Solte o zip na pasta plugins\ do repo"
    Write-Host "        3. Rode o BLOOM.bat de novo - os .vrm entram na fila sozinhos"
}
if ($faltando.Count -gt 0 -and $Blender) {
    for ($i = 0; $i -lt $faltando.Count; $i++) {
        $mb = [math]::Round($faltando[$i].Length / 1MB)
        Write-Host ("    {0}. [{1}] {2} MB  {3}" -f ($i+1), $faltando[$i].LastWriteTime.ToString("dd/MM HH:mm"), $mb, $faltando[$i].FullName)
    }
    $resp = Read-Host "  Fazer raio-X de qual? (numero / A = todos / Enter = pular)"
    $escolhidos = @()
    if ($resp -eq "A" -or $resp -eq "a") { $escolhidos = $faltando }
    elseif ($resp -match '^\d+$') {
        $n = [int]$resp
        if ($n -ge 1 -and $n -le $faltando.Count) { $escolhidos = @($faltando[$n-1]) }
    }
    foreach ($m in $escolhidos) {
        $nome = [regex]::Replace([System.IO.Path]::GetFileNameWithoutExtension($m.Name), "[^\w\-]", "_").Trim("_")
        $saida = Join-Path $Probes ("model_probe_{0}.json" -f $nome)
        Write-Host "        Raio-X: $($m.Name) ..."
        if ($m.Extension -ieq ".vrm") {
            & $Blender --background --python (Join-Path $Repo "util\probe_vrm.py") -- --vrm $m.FullName --out $saida 2>&1 |
                Where-Object { $_ -match "MODEL PROBE|salvo|\[X\]" } | ForEach-Object { Write-Host "          $_" }
        } else {
            & $Blender --background --factory-startup $m.FullName --python (Join-Path $Repo "tools\model_probe.py") -- --out $saida 2>&1 |
                Where-Object { $_ -match "MODEL PROBE|salvo|\[X\]" } | ForEach-Object { Write-Host "          $_" }
        }
        if (Test-Path $saida) { Write-Host "          OK: $saida" -ForegroundColor Green }
        else { Write-Host "          FALHOU (me mande um print desta janela na conversa)" -ForegroundColor Red }
    }
} elseif ($faltando.Count -gt 0) {
    Write-Host "        Sem Blender nao da pra rodar o raio-X; deixo pra proxima." -ForegroundColor Yellow
}

# ---------- [5/6] ativar CI (so na primeira vez) ----------
$ciFonte = Join-Path $Repo "tools\ci\tests.yml"
$ciDestino = Join-Path $Repo ".github\workflows\tests.yml"
if ((Test-Path $ciFonte) -and (-not (Test-Path $ciDestino))) {
    Write-Host "  [6/7] Ativando o CI do GitHub (testes a cada push)..."
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ciDestino) | Out-Null
    Push-Location $Repo
    git mv "tools/ci/tests.yml" ".github/workflows/tests.yml" 2>&1 | Out-Null
    Pop-Location
    if (Test-Path $ciDestino) { Write-Host "        CI pronto (sai no proximo sync)." -ForegroundColor Green }
} else {
    Write-Host "  [6/7] CI: nada a fazer."
}

# ---------- [6/6] commit + push ----------
Write-Host "  [7/7] Sincronizando (commit+push do que surgir)..."
if ($py) {
    Push-Location $Repo
    & $py "tools\project_cli.py" sync -m "bloom: rotina unica (probes/relatorios, plugins, ci)"
    Pop-Location
} else {
    Write-Host "        [!] Sem Python; rode o DevKit.bat pra sincronizar." -ForegroundColor Yellow
}

# ---------- abrir o Blender? ----------
Write-Host ""
if ($Blender) {
    $abrir = Read-Host "  Abrir o Blender agora? (S/n)"
    if ($abrir -ne "n" -and $abrir -ne "N") {
        Start-Process $Blender
        Write-Host "  Blender abrindo... no painel N > Bloom voce fala com o agent."
    }
}
Write-Host ""
Write-Host "  Rotina concluida. Log salvo em: $Log" -ForegroundColor Cyan
Write-Host "  Addon: se a versao mudou (v0.3.2), feche e abra o Blender." 
try { Stop-Transcript | Out-Null } catch { }
Get-ChildItem $Logs -Filter "bloom_*.txt" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 10 |
    Remove-Item -Force -ErrorAction SilentlyContinue
