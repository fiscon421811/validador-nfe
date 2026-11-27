# Gera o executável do Validador de NF-e para Windows.
#
# Uso, na pasta do projeto, no PowerShell:
#   powershell -ExecutionPolicy Bypass -File ferramentas\gerar_exe.ps1
# ou, com outro Python:
#   powershell -ExecutionPolicy Bypass -File ferramentas\gerar_exe.ps1 -Py "C:\caminho\python.exe"
#
# Resultado: dist\ValidadorNFe.exe

param(
    [string]$Py = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path $Py)) {
    Write-Error "Python não encontrado em $Py. Passe o caminho com -Py."
}

Write-Host "1/4 Instalando dependências..." -ForegroundColor Cyan
& $Py -m pip install -e ".[gui,exe]"
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependências" }

Write-Host "2/4 Rodando os testes..." -ForegroundColor Cyan
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Testes falharam; executável não gerado" }

Write-Host "3/4 Gerando o ícone..." -ForegroundColor Cyan
& $Py ferramentas\gerar_icone.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o ícone" }

Write-Host "4/4 Empacotando (pode levar alguns minutos)..." -ForegroundColor Cyan
& $Py -m flet_cli.cli pack app_gui.py `
    --name ValidadorNFe `
    --icon assets\icone.ico `
    --add-data "regras:regras" `
    --product-name "Validador de NF-e" `
    --file-description "Validação da tributação de NF-e" `
    --product-version "0.1.0" `
    --file-version "0.1.0.0" `
    --copyright "Edson Ortolan" `
    -y
if ($LASTEXITCODE -ne 0) { throw "Falha no empacotamento" }

Write-Host ""
Write-Host "Pronto: $(Resolve-Path dist\ValidadorNFe.exe)" -ForegroundColor Green
