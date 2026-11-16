[CmdletBinding()]
param([string]$Pasta = $PSScriptRoot)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($Pasta).TrimEnd([char[]]@('\','/')) + [IO.Path]::DirectorySeparatorChar
$manifest = Join-Path $root 'MANIFESTO.csv'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw 'MANIFESTO.csv nao encontrado.' }
$rows = @(Import-Csv -LiteralPath $manifest -Encoding UTF8)
if ($rows.Count -eq 0) { throw 'Manifesto vazio.' }
$count = 0
foreach ($row in $rows) {
    $path = [IO.Path]::GetFullPath((Join-Path $root $row.Caminho))
    if (-not $path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Caminho fora da pasta no manifesto.'
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Falta: $($row.Caminho)" }
    if ((Get-Item -LiteralPath $path).Length -ne [long]$row.TamanhoBytes) { throw "Tamanho diferente: $($row.Caminho)" }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $row.SHA256) { throw "SHA256 diferente: $($row.Caminho)" }
    $count++
}
Write-Host "$count ficheiros do manifesto conferidos com sucesso." -ForegroundColor Green
