param(
    [string]$Database
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")
Assert-LockedPython
$python = $script:LockedPython
$arguments = @("-X", "utf8", (Join-Path $PSScriptRoot "catalog_check.py"))
if ($Database) {
    $arguments += @("--database", $Database)
}
& $python @arguments
exit $LASTEXITCODE
