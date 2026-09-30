. (Join-Path $PSScriptRoot '_common.ps1')
Assert-LockedPython
$env:PYTHONPYCACHEPREFIX = Join-Path ([System.IO.Path]::GetTempPath()) 'nl_project_2_check_pycache'
$env:RUFF_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) 'nl_project_2_ruff_cache'
& $script:LockedPython -m compileall -q src tests tools
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $script:LockedPython -m ruff check src tests tools
exit $LASTEXITCODE
