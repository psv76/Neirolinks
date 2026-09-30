. (Join-Path $PSScriptRoot '_common.ps1')
Assert-LockedPython
& $script:LockedPython -m ruff format --check src tests tools
exit $LASTEXITCODE

