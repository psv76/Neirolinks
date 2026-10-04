. (Join-Path $PSScriptRoot '_common.ps1')
Assert-LockedPython
$dist = Join-Path $script:RepositoryRoot 'dist'
$distTarget = Join-Path $dist 'NLProject3'
$work = Join-Path $script:RepositoryRoot 'build\pyinstaller'
$analysisToc = Join-Path $work 'nl_project_3\Analysis-00.toc'

foreach ($generatedPath in @($distTarget, $work)) {
    $fullGeneratedPath = [IO.Path]::GetFullPath($generatedPath)
    if (-not $fullGeneratedPath.StartsWith(
        $script:RepositoryRoot + '\',
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Generated path escapes repository root: $fullGeneratedPath"
    }
    if (Test-Path -LiteralPath $fullGeneratedPath) {
        Remove-Item -LiteralPath $fullGeneratedPath -Recurse -Force
    }
}

& $script:LockedPython -X utf8 (Join-Path $PSScriptRoot 'prepare_compliance_sources.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:PYINSTALLER_CONFIG_DIR = Join-Path $script:RepositoryRoot '.cache\pyinstaller'
& $script:LockedPython -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $script:RepositoryRoot 'packaging\nl_project_3.spec')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $script:LockedPython -X utf8 (Join-Path $PSScriptRoot 'package_compliance.py') `
    --dist $distTarget --analysis-toc $analysisToc
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot 'inventory.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $script:LockedPython -X utf8 (Join-Path $PSScriptRoot 'package_compliance.py') `
    --dist $distTarget --validate-only
exit $LASTEXITCODE
