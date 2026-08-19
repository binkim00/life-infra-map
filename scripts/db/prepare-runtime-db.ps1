[CmdletBinding()]
param(
    [string]$Container = "life-infra-map-db",
    [string]$DbUser = "life_infra_map",
    [string]$SourceDatabase = "life_infra_map",
    [string]$TargetDatabase = "life_infra_map_runtime",
    [string]$OutputDirectory = "backend/tmp/db",
    [switch]$VerifyOnly,
    [switch]$SkipDump
)

$ErrorActionPreference = "Stop"

function Assert-SafeIdentifier {
    param([string]$Value, [string]$Name)

    if ($Value -notmatch '^[a-zA-Z_][a-zA-Z0-9_]*$') {
        throw "$Name must be a PostgreSQL-safe identifier: $Value"
    }
}

function Invoke-Docker {
    param([string[]]$Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker command failed with exit code $LASTEXITCODE"
    }
}

function Read-Scalar {
    param([string]$Database, [string]$Sql)

    $value = & docker exec $Container psql -U $DbUser -d $Database -Atqc $Sql
    if ($LASTEXITCODE -ne 0) {
        throw "Database query failed for $Database"
    }
    return ($value | Select-Object -First 1).Trim()
}

Assert-SafeIdentifier $DbUser "DbUser"
Assert-SafeIdentifier $SourceDatabase "SourceDatabase"
Assert-SafeIdentifier $TargetDatabase "TargetDatabase"

if ($SourceDatabase -eq $TargetDatabase) {
    throw "SourceDatabase and TargetDatabase must be different."
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$outputPath = Join-Path $repositoryRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

& docker inspect $Container | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker container is not available: $Container"
}

$sourceExists = & docker exec $Container psql -U $DbUser -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = '$SourceDatabase'"
if ($LASTEXITCODE -ne 0 -or ($sourceExists | Select-Object -First 1) -ne "1") {
    throw "Source database does not exist: $SourceDatabase"
}

$targetExists = & docker exec $Container psql -U $DbUser -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = '$TargetDatabase'"
if ($LASTEXITCODE -ne 0) {
    throw "Could not check target database."
}
if (($targetExists | Select-Object -First 1) -eq "1") {
    if (-not $VerifyOnly) {
        throw "Target database already exists: $TargetDatabase. Use -VerifyOnly or a new target name; this script never overwrites a database."
    }
    Write-Host "Using existing runtime database for verification: $TargetDatabase"
} elseif ($VerifyOnly) {
    throw "VerifyOnly target database does not exist: $TargetDatabase"
} else {
    Write-Host "Creating empty runtime database: $TargetDatabase"
    Invoke-Docker @("exec", $Container, "createdb", "-U", $DbUser, "-T", "template0", $TargetDatabase)

    $cloneCommand = @"
set -eu
pg_dump -U "$DbUser" -d "$SourceDatabase" \
  --no-owner --no-privileges \
  --exclude-table-data=public.recommendations_sourceplacerecord \
  --exclude-table-data=public.recommendations_kakaoplacematch \
| psql -q -v ON_ERROR_STOP=1 -U "$DbUser" -d "$TargetDatabase"
"@

    Write-Host "Copying service data while leaving raw source rows empty."
    Invoke-Docker @("exec", $Container, "sh", "-ec", $cloneCommand)
}

$preservedTables = @(
    "recommendations_place",
    "recommendations_tag",
    "recommendations_placetag",
    "recommendations_placetagevidence",
    "recommendations_placetagcollectionjob",
    "recommendations_providerquotausage",
    "accounts_userprofile",
    "auth_user",
    "boards_post"
)

Write-Host "Verifying preserved row counts."
foreach ($table in $preservedTables) {
    Assert-SafeIdentifier $table "table"
    $sourceCount = Read-Scalar $SourceDatabase "SELECT count(*) FROM $table"
    $targetCount = Read-Scalar $TargetDatabase "SELECT count(*) FROM $table"
    if ($sourceCount -ne $targetCount) {
        throw "Row-count mismatch for $table (source=$sourceCount target=$targetCount)"
    }
    Write-Host "  $table = $targetCount"
}

foreach ($table in @("recommendations_sourceplacerecord", "recommendations_kakaoplacematch")) {
    $targetCount = Read-Scalar $TargetDatabase "SELECT count(*) FROM $table"
    if ($targetCount -ne "0") {
        throw "Excluded table is not empty: $table=$targetCount"
    }
    Write-Host "  $table = 0 (archive-only)"
}

$postgisVersion = Read-Scalar $TargetDatabase "SELECT PostGIS_Version()"
$databaseSize = Read-Scalar $TargetDatabase "SELECT pg_size_pretty(pg_database_size(current_database()))"
Write-Host "PostGIS: $postgisVersion"
Write-Host "Runtime database size: $databaseSize"

if ($SkipDump) {
    Write-Host "Runtime database ready: $TargetDatabase"
    exit 0
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpName = "$TargetDatabase-$timestamp.dump"
$containerDump = "/tmp/$dumpName"
$hostDump = Join-Path $outputPath $dumpName

try {
    Write-Host "Creating deployable custom-format dump."
    Invoke-Docker @(
        "exec", $Container,
        "pg_dump", "-U", $DbUser, "-d", $TargetDatabase,
        "--format=custom", "--compress=6", "--no-owner", "--no-privileges",
        "--file", $containerDump
    )
    Invoke-Docker @("cp", "${Container}:$containerDump", $hostDump)
} finally {
    & docker exec $Container rm -f $containerDump | Out-Null
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $hostDump).Hash.ToLowerInvariant()
$hashFile = "$hostDump.sha256"
Set-Content -LiteralPath $hashFile -Encoding ascii -Value "$hash  $dumpName"

Write-Host "Runtime database ready: $TargetDatabase"
Write-Host "Deployment dump: $hostDump"
Write-Host "SHA256: $hash"
