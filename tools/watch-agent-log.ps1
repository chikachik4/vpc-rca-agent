param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("codex", "gemini")]
    [string] $Agent,

    [string] $Team = $env:AGENT_TEAM,
    [int] $Tail = 80
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Team)) {
    $Team = "default"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $repoRoot ".agents-dev\log\$Team"
$currentPath = $null
$offset = 0L

function Get-LatestLog {
    if (-not (Test-Path $logDir)) {
        return $null
    }

    Get-ChildItem -Path $logDir -Filter "$Agent-*.log" -File |
        Sort-Object LastWriteTimeUtc, Name -Descending |
        Select-Object -First 1
}

function Show-Tail {
    param([System.IO.FileInfo] $File)

    Clear-Host
    Write-Host "Watching $Agent logs for team '$Team'"
    Write-Host $File.FullName
    Write-Host ""

    Get-Content -Path $File.FullName -Tail $Tail | Out-Host
    return $File.Length
}

Write-Host "Waiting for $Agent logs in $logDir ..."

while ($true) {
    $latest = Get-LatestLog

    if ($null -eq $latest) {
        Start-Sleep -Seconds 1
        continue
    }

    if ($currentPath -ne $latest.FullName) {
        $currentPath = $latest.FullName
        $offset = Show-Tail -File $latest
    }

    $latest.Refresh()
    if ($latest.Length -lt $offset) {
        $offset = Show-Tail -File $latest
    }

    if ($latest.Length -gt $offset) {
        $stream = [System.IO.File]::Open($latest.FullName, "Open", "Read", "ReadWrite")
        try {
            $stream.Seek($offset, [System.IO.SeekOrigin]::Begin) | Out-Null
            $reader = [System.IO.StreamReader]::new($stream)
            $text = $reader.ReadToEnd()
            if ($text.Length -gt 0) {
                Write-Host -NoNewline $text
            }
            $offset = $stream.Position
        }
        finally {
            if ($reader) {
                $reader.Dispose()
            }
            $stream.Dispose()
        }
    }

    Start-Sleep -Milliseconds 500
}
