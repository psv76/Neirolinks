param(
    [string]$RootPath = 'dist\NLProject3',
    [string]$OutputPath = 'PACKAGE_MANIFEST_SHA256.tsv'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$root = (Resolve-Path -LiteralPath (Join-Path $repositoryRoot $RootPath)).Path
if (-not $root.StartsWith($repositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Inventory root escapes repository root: $root"
}
$output = [IO.Path]::GetFullPath((Join-Path $root $OutputPath))
if (-not $output.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Manifest path escapes repository root: $output"
}
$lines = [Collections.Generic.List[string]]::new()
$lines.Add("relative_path`tbytes`tsha256")
$files = Get-ChildItem -LiteralPath $root -Recurse -File -Force |
    Where-Object { $_.FullName -ne $output } |
    Sort-Object FullName
foreach ($file in $files) {
    $relative = $file.FullName.Substring($root.Length).TrimStart('\')
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    $lines.Add("$relative`t$($file.Length)`t$hash")
}
[IO.File]::WriteAllLines($output, $lines, [Text.UTF8Encoding]::new($false))
Write-Output "Manifest root: $root"
Write-Output "Manifest entries: $($files.Count)"
