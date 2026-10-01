param([int]$AutoCloseMilliseconds = 0)
. (Join-Path $PSScriptRoot '_common.ps1')
Assert-LockedPython
& $script:LockedPython -m nl_project_2 --auto-close-ms $AutoCloseMilliseconds
exit $LASTEXITCODE

