. (Join-Path $PSScriptRoot '_common.ps1')
Assert-LockedPython
& $script:LockedPython (Join-Path $PSScriptRoot 'autocad_contract_check.py')
exit $LASTEXITCODE
