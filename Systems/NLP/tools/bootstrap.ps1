param([switch]$Recreate)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$lock = Get-Content -LiteralPath (Join-Path $root 'runtime.lock.json') -Raw | ConvertFrom-Json
$cache = Join-Path $root '.cache'
$package = Join-Path $cache "python.$($lock.version).nupkg"
$runtime = Join-Path $root ".runtime\python-$($lock.version)"
$runtimePython = Join-Path $runtime ($lock.python_relative_path -replace '/', '\')
$venv = Join-Path $root '.venv'

foreach ($generatedPath in @($cache, $runtime, $venv)) {
    $fullGeneratedPath = [IO.Path]::GetFullPath($generatedPath)
    if (-not $fullGeneratedPath.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Generated path escapes repository root: $fullGeneratedPath"
    }
}

New-Item -ItemType Directory -Path $cache -Force | Out-Null
if (-not (Test-Path -LiteralPath $package)) {
    & curl.exe -L --fail --silent --show-error $lock.url -o $package
    if ($LASTEXITCODE -ne 0) { throw "Runtime download failed with exit code $LASTEXITCODE." }
}
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $package).Hash.ToLowerInvariant()
if ($actualHash -ne $lock.sha256) { throw "Runtime SHA-256 mismatch: $actualHash" }

if ($Recreate -and (Test-Path -LiteralPath $runtime)) {
    Remove-Item -LiteralPath $runtime -Recurse -Force
}
if (-not (Test-Path -LiteralPath $runtimePython)) {
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    & tar.exe -xf $package -C $runtime
    if ($LASTEXITCODE -ne 0) { throw "Runtime extraction failed with exit code $LASTEXITCODE." }
}
if ($Recreate -and (Test-Path -LiteralPath $venv)) {
    Remove-Item -LiteralPath $venv -Recurse -Force
}
if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
    & $runtimePython -m venv $venv
}

$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --disable-pip-version-check --require-hashes -r (Join-Path $root 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw "Locked dependency installation failed: $LASTEXITCODE" }
& $python -c "import platform; assert platform.python_version() == '3.13.14'; assert platform.architecture()[0] == '64bit'; print(platform.python_version())"
if ($LASTEXITCODE -ne 0) { throw "Runtime verification failed: $LASTEXITCODE" }
