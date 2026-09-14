<#
.SYNOPSIS
    Roda o portao de qualidade inteiro do Curupira, na ordem do CI.
.DESCRIPTION
    Nada entra na main sem passar aqui. Para no primeiro erro, para voce corrigir
    uma coisa de cada vez em vez de encarar uma parede de saida.

    Rode SEMPRE com o venv do projeto ativo. A primeira etapa confere isso.

    CACHES FORA DA PASTA DO PROJETO
    -------------------------------
    ruff, mypy, pytest e coverage escrevem cache em disco. Dentro de uma pasta
    sincronizada (OneDrive, Dropbox, Google Drive) isso gera duas dores: churn de
    sincronizacao a cada rodada, e — pior — o cliente de sync segura o handle no
    meio de um rename e a ferramenta leva "Acesso negado".

    Este script aponta todos os caches para %LOCALAPPDATA%\curupira\cache, que
    nunca sincroniza. Funciona igual em pasta sincronizada ou nao, entao nao ha
    ramificacao nem deteccao fragil: e simplesmente o lugar certo para cache.
.EXAMPLE
    .\scripts\portao.ps1
.EXAMPLE
    .\scripts\portao.ps1 -Rapido   # pula o pip-audit, que vai na rede
#>
[CmdletBinding()]
param(
    [switch]$Rapido
)

$raiz = Split-Path -Parent $PSScriptRoot
Push-Location $raiz

$cache = Join-Path $env:LOCALAPPDATA "curupira\cache"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$env:RUFF_CACHE_DIR  = Join-Path $cache "ruff"
$env:MYPY_CACHE_DIR  = Join-Path $cache "mypy"
$env:COVERAGE_FILE   = Join-Path $cache ".coverage"
$cachePytest         = Join-Path $cache "pytest"

Write-Host "caches em: $cache" -ForegroundColor DarkGray

$etapas = @(
    @{ Nome = "versoes pinadas"; Cmd = { python scripts/checar_versoes.py } }
    @{ Nome = "ruff (lint)";     Cmd = { ruff check . } }
    @{ Nome = "ruff (format)";   Cmd = { ruff format --check . } }
    @{ Nome = "mypy --strict";   Cmd = { python -m mypy } }
    @{ Nome = "bandit";          Cmd = { python -m bandit -c pyproject.toml -q -r src scripts } }
    @{ Nome = "pytest";          Cmd = { python -m pytest -o cache_dir="$cachePytest" } }
)
if (-not $Rapido) {
    $etapas += @{ Nome = "pip-audit"; Cmd = { python -m pip_audit --skip-editable --progress-spinner off } }
}

$falha = $null
try {
    foreach ($etapa in $etapas) {
        Write-Host ""
        Write-Host ("=" * 62) -ForegroundColor DarkGray
        Write-Host "  $($etapa.Nome)" -ForegroundColor Cyan
        Write-Host ("=" * 62) -ForegroundColor DarkGray

        $global:LASTEXITCODE = 0
        try {
            & $etapa.Cmd
        }
        catch {
            Write-Host $_.Exception.Message -ForegroundColor Red
            $falha = "$($etapa.Nome) (ferramenta nao encontrada - o venv esta ativo?)"
            break
        }
        if ($LASTEXITCODE -ne 0) {
            $falha = $etapa.Nome
            break
        }
    }
}
finally {
    Pop-Location
}

Write-Host ""
if ($falha) {
    Write-Host "PORTAO FECHADO em: $falha" -ForegroundColor Red
    exit 1
}
Write-Host "PORTAO ABERTO. Pode commitar." -ForegroundColor Green
