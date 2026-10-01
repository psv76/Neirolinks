$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Assert-LockedPython

if ($args.Count -ne 1) {
    throw 'Usage: tools\db-check.ps1 <path-to-sqlite>'
}

& $script:LockedPython (Join-Path $PSScriptRoot 'db_check.py') $args[0]
exit $LASTEXITCODE

