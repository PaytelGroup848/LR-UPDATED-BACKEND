param(
    [int]$PollSeconds = 10,
    [int]$QuietSeconds = 20,
    [switch]$BuildOnStart,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$LogDir = Join-Path $ProjectRoot "instance\logs"
$LogFile = Join-Path $LogDir "auto_update_build.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            Add-Content -Path $LogFile -Value $line
            break
        }
        catch {
            if ($attempt -eq 4) { throw }
            Start-Sleep -Milliseconds 200
        }
    }
    Write-Host $line
}

function Get-SourceHash {
    param(
        [string]$Root,
        [string[]]$Include
    )

    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            $files = foreach ($pattern in $Include) {
                Get-ChildItem -Path $Root -Recurse -File -Include $pattern -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.FullName -notmatch '\\(__pycache__|build|dist|specs|work)\\' -and
                        $_.Name -ne "build_version.py"
                    }
            }

            $fingerprint = $files |
                Sort-Object FullName |
                ForEach-Object {
                    $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
                    "{0}:{1}:{2}" -f $_.FullName.Substring($ProjectRoot.Path.Length), $_.Length, $hash
                }

            $bytes = [System.Text.Encoding]::UTF8.GetBytes(($fingerprint -join "`n"))
            $sha = [System.Security.Cryptography.SHA256]::Create()
            try {
                return [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
            }
            finally {
                $sha.Dispose()
            }
        }
        catch {
            if ($attempt -eq 4) { throw }
            Start-Sleep -Milliseconds 200
        }
    }
}

function Wait-ForStableSourceHash {
    param(
        [string]$Root,
        [string[]]$Include,
        [string]$InitialHash,
        [int]$QuietForSeconds
    )

    if ($QuietForSeconds -le 0) {
        return $InitialHash
    }

    $lastHash = $InitialHash
    $stableSince = [DateTime]::UtcNow
    Write-Log "Source change detected. Waiting $QuietForSeconds seconds for edits to settle..."

    while (([DateTime]::UtcNow - $stableSince).TotalSeconds -lt $QuietForSeconds) {
        Start-Sleep -Milliseconds 500
        $nextHash = Get-SourceHash -Root $Root -Include $Include
        if ($nextHash -ne $lastHash) {
            $lastHash = $nextHash
            $stableSince = [DateTime]::UtcNow
            Write-Log "More source changes detected. Stability timer restarted."
        }
    }

    return $lastHash
}

function Build-AdminPanel {
    Write-Log "Admin Panel source changed. Building package..."
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & python (Join-Path $ProjectRoot "installer\build\build_admin_panel.py") 2>&1 |
        ForEach-Object { Write-Log "ADMIN: $_" }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($exitCode -ne 0) {
        throw "Admin Panel build failed with exit code $exitCode"
    }
    Write-Log "Admin Panel package published."
}

function Build-DesktopClient {
    Write-Log "Desktop Client source changed. Building package..."
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "desktop-client\build_client.ps1") 2>&1 |
        ForEach-Object { Write-Log "DESKTOP: $_" }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($exitCode -ne 0) {
        throw "Desktop Client build failed with exit code $exitCode"
    }
    Write-Log "Desktop Client package published."
}

$AdminRoot = Join-Path $ProjectRoot "admin-panel"
$DesktopRoot = Join-Path $ProjectRoot "desktop-client"
$AdminHash = Get-SourceHash -Root $AdminRoot -Include @("*.py", "*.png", "*.ico")
$DesktopHash = Get-SourceHash -Root $DesktopRoot -Include @("*.py", "*.png", "*.ico")

Write-Log "Auto update publisher started. PollSeconds=$PollSeconds QuietSeconds=$QuietSeconds BuildOnStart=$BuildOnStart Once=$Once"

if ($BuildOnStart) {
    Build-AdminPanel
    Build-DesktopClient
    $AdminHash = Get-SourceHash -Root $AdminRoot -Include @("*.py", "*.png", "*.ico")
    $DesktopHash = Get-SourceHash -Root $DesktopRoot -Include @("*.py", "*.png", "*.ico")
}

do {
    Start-Sleep -Seconds $PollSeconds

    $nextAdminHash = Get-SourceHash -Root $AdminRoot -Include @("*.py", "*.png", "*.ico")
    $nextDesktopHash = Get-SourceHash -Root $DesktopRoot -Include @("*.py", "*.png", "*.ico")

    if ($nextAdminHash -ne $AdminHash) {
        $stableAdminHash = Wait-ForStableSourceHash `
            -Root $AdminRoot `
            -Include @("*.py", "*.png", "*.ico") `
            -InitialHash $nextAdminHash `
            -QuietForSeconds $QuietSeconds
        try {
            Build-AdminPanel
            $publishedAdminHash = Get-SourceHash -Root $AdminRoot -Include @("*.py", "*.png", "*.ico")
            if ($publishedAdminHash -ne $stableAdminHash) {
                throw "Admin Panel source changed while building; a new build is required"
            }
            $AdminHash = $publishedAdminHash
        }
        catch {
            Write-Log "ADMIN ERROR: $_"
        }
    }

    if ($nextDesktopHash -ne $DesktopHash) {
        $stableDesktopHash = Wait-ForStableSourceHash `
            -Root $DesktopRoot `
            -Include @("*.py", "*.png", "*.ico") `
            -InitialHash $nextDesktopHash `
            -QuietForSeconds $QuietSeconds
        try {
            Build-DesktopClient
            $publishedDesktopHash = Get-SourceHash -Root $DesktopRoot -Include @("*.py", "*.png", "*.ico")
            if ($publishedDesktopHash -ne $stableDesktopHash) {
                throw "Desktop Client source changed while building; a new build is required"
            }
            $DesktopHash = $publishedDesktopHash
        }
        catch {
            Write-Log "DESKTOP ERROR: $_"
        }
    }
}
while (-not $Once)

Write-Log "Auto update publisher stopped."
