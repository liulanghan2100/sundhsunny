param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [string]$SolutionPath,
    [string]$TestProjectPath,
    [string]$PublishPath,
    [string]$BackupPattern,
    [string[]]$DocPaths = @()
)

# If local execution policy blocks direct invocation, run this script with:
# powershell -NoProfile -ExecutionPolicy Bypass -Command "& '<path>/gate_check.ps1' ..."
# This bypass is process-scoped and does not require administrator rights.

$ErrorActionPreference = "Stop"

function Add-Result {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )
    $Results.Add([pscustomobject]@{
        name = $Name
        passed = $Passed
        detail = $Detail
    }) | Out-Null
}

function Test-Utf8Document {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path)) {
        return "missing"
    }
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $Path))
    if ($bytes.Length -eq 0) {
        return "empty"
    }
    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    try {
        $text = $utf8.GetString($bytes)
    }
    catch {
        return "invalid utf8"
    }
    if ($text.Contains([char]0xFFFD)) {
        return "contains replacement character"
    }
    return "ok"
}

$project = Resolve-Path $ProjectPath
$results = [System.Collections.Generic.List[object]]::new()

if ($SolutionPath) {
    Push-Location $project
    try {
        $buildOutput = & dotnet build $SolutionPath --no-restore 2>&1
        Add-Result $results "build" ($LASTEXITCODE -eq 0) (($buildOutput | Select-Object -Last 20) -join "`n")
    }
    finally {
        Pop-Location
    }
}

if ($TestProjectPath) {
    Push-Location $project
    try {
        $testOutput = & dotnet run --no-build --project $TestProjectPath 2>&1
        Add-Result $results "smoke_test" ($LASTEXITCODE -eq 0) (($testOutput | Select-Object -Last 20) -join "`n")
    }
    finally {
        Pop-Location
    }
}

if ($PublishPath) {
    $publish = Join-Path $project $PublishPath
    $exe = Get-ChildItem -LiteralPath $publish -Filter *.exe -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Add-Result $results "publish" ($null -ne $exe -and $exe.Length -gt 0) ($(if ($exe) { $exe.FullName } else { "no exe found in $publish" }))
}

if ($BackupPattern) {
    $backup = Get-ChildItem -Path $BackupPattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Add-Result $results "backup" ($null -ne $backup -and $backup.Length -gt 0) ($(if ($backup) { "$($backup.FullName) bytes=$($backup.Length)" } else { "no backup matched $BackupPattern" }))
}

foreach ($doc in $DocPaths) {
    $docPath = Join-Path $project $doc
    $status = Test-Utf8Document $docPath
    Add-Result $results "doc:$doc" ($status -eq "ok") $status
}

$reportDir = Join-Path $project "09_research/expert_dev_p0/reports"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$reportPath = Join-Path $reportDir ("gate_report_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$summary = [pscustomobject]@{
    project_path = $project.Path
    generated_at = (Get-Date).ToString("s")
    passed = -not ($results | Where-Object { -not $_.passed })
    results = $results
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 5

if (-not $summary.passed) {
    exit 1
}
