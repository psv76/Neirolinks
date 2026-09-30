$ErrorActionPreference = 'Stop'
$script:RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$script:LockedPython = Join-Path $script:RepositoryRoot '.venv\Scripts\python.exe'

function Assert-LockedPython {
    if (-not (Test-Path -LiteralPath $script:LockedPython)) {
        throw 'Locked environment is absent. Run tools\bootstrap.ps1 first.'
    }
    $version = & $script:LockedPython -c "import platform; print(platform.python_version()); print(platform.architecture()[0])"
    if ($version[0] -ne '3.13.14' -or $version[1] -ne '64bit') {
        throw "Expected CPython 3.13.14 x64, got $($version -join ' ')."
    }
    $env:PYTHONPATH = Join-Path $script:RepositoryRoot 'src'
}

