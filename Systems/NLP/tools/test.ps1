param([string]$MarkerExpression = 'not live_cad and not manual_acceptance')
. (Join-Path $PSScriptRoot '_common.ps1')
Assert-LockedPython
& $script:LockedPython -m pytest -m $MarkerExpression
exit $LASTEXITCODE

