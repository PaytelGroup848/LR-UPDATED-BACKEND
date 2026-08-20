import json
import platform
import re
import subprocess
import tempfile
from pathlib import Path


INVALID_USERNAME_CHARS = re.compile(r'[\\/"\[\]:;|=,+*?<>@]')


def _clean_text(value):
    return str(value or "").strip()


def _created_account_identity(output):
    for line in reversed(str(output or "").splitlines()):
        try:
            data = json.loads(line.strip())
        except (TypeError, ValueError):
            continue
        scope = _clean_text(data.get("scope")).lower()
        if scope in {"local", "domain"}:
            return {
                "windows_account_scope": scope,
                "windows_domain": (
                    _clean_text(data.get("domain"))
                    if scope == "domain"
                    else None
                ),
            }
    return {}


def create_windows_user(username, password, full_name="", description=""):
    username = _clean_text(username)
    password = str(password or "")

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "message": "Agent must run on Windows to create Windows accounts.",
        }

    if not username or not password:
        return {
            "success": False,
            "message": "Windows username and password are required.",
        }

    if len(username) > 20 or INVALID_USERNAME_CHARS.search(username) or username.endswith("."):
        return {
            "success": False,
            "message": "Windows username is invalid. Use 1-20 characters without special Windows account symbols.",
        }

    result = _run_account_script(
        username,
        password,
        full_name or username,
        description or "LR Remote published-app user",
    )

    if result.returncode == 0:
        return {
            "success": True,
            "message": "Windows account created",
            **_created_account_identity(result.stdout),
        }
    if result.returncode == 10:
        return {"success": False, "message": "Windows username already exists"}

    detail = (result.stderr or result.stdout or "").strip()
    if "InvalidPasswordException" in detail or "FullyQualifiedErrorId : InvalidPassword" in detail:
        return {
            "success": False,
            "message": (
                "Windows rejected this password. Use a stronger password that meets the local Windows policy, "
                "for example 8+ characters with uppercase, lowercase, number, and symbol."
            ),
        }
    return {
        "success": False,
        "message": f"Windows account creation failed: {detail or 'PowerShell returned an error'}",
    }


def _run_account_script(username, password, full_name, description):
    script = r"""param(
    [string]$name,
    [string]$plain,
    [string]$full,
    [string]$desc
)
$ErrorActionPreference = 'Stop'
if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) { exit 10 }
$secure = ConvertTo-SecureString $plain -AsPlainText -Force
New-LocalUser -Name $name -Password $secure -FullName $full -Description $desc -PasswordNeverExpires:$true | Out-Null
Add-LocalGroupMember -Group 'Remote Desktop Users' -Member $name -ErrorAction SilentlyContinue
$account = Get-LocalUser -Name $name

# 1. Ensure C:\Users\$name\Desktop exists
$desktopFolder = "C:\Users\$name\Desktop"
if (-not (Test-Path -LiteralPath $desktopFolder)) {
    New-Item -ItemType Directory -Path $desktopFolder -Force -ErrorAction SilentlyContinue | Out-Null
}

# 2. Lock down Documents, Downloads, Pictures, Music, Videos for $name using icacls
$subFolders = @("Documents", "Downloads", "Pictures", "Music", "Videos", "3D Objects")
foreach ($folder in $subFolders) {
    $targetPath = "C:\Users\$name\$folder"
    if (Test-Path -LiteralPath $targetPath) {
        & icacls.exe "$targetPath" /inheritance:r /grant:r "Administrators:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F" /Q | Out-Null
    }
}

# 3. Grant $name Full Control ONLY on Desktop folder
& icacls.exe "$desktopFolder" /grant "${name}:(OI)(CI)F" /Q | Out-Null

# 4. Hide 3D Objects, Documents, Downloads, Music, Pictures, Videos from This PC machine-wide
$folderGUIDs = @(
    '{31C08077-0A78-432C-8014-3994406B950B}',
    '{f424662b-460b-47f6-804e-570b130e809a}',
    '{7d83edd9-0016-440d-a320-309d57a903c7}',
    '{088e3905-0323-4b02-9826-5d99428e115f}',
    '{374DE290-123F-4565-9164-39C4925E467B}',
    '{0ddd015d-b061-4772-943f-ee0ac5523165}',
    '{a0c69a99-21c8-4672-8703-4672b39562c3}',
    '{35286144-4610-4836-9e71-a8354f3d2e71}'
)
foreach ($guid in $folderGUIDs) {
    $bagPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FolderDescriptions\$guid\PropertyBag"
    if (Test-Path -LiteralPath $bagPath) {
        New-ItemProperty -LiteralPath $bagPath -Name "ThisPCPolicy" -Value "Hide" -Force -ErrorAction SilentlyContinue | Out-Null
    }
    $bagPath64 = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Explorer\FolderDescriptions\$guid\PropertyBag"
    if (Test-Path -LiteralPath $bagPath64) {
        New-ItemProperty -LiteralPath $bagPath64 -Name "ThisPCPolicy" -Value "Hide" -Force -ErrorAction SilentlyContinue | Out-Null
    }
}

# 5. Ensure HKLM policy is clean (NoDrives deleted) & HubMode/NoNetHood enabled
$hklmExplorer = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer'
New-Item -Path $hklmExplorer -Force -ErrorAction SilentlyContinue | Out-Null
Remove-ItemProperty -LiteralPath $hklmExplorer -Name 'NoDrives' -ErrorAction SilentlyContinue
Remove-ItemProperty -LiteralPath $hklmExplorer -Name 'NoViewOnDrive' -ErrorAction SilentlyContinue
New-ItemProperty -LiteralPath $hklmExplorer -Name 'HubMode' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
New-ItemProperty -LiteralPath $hklmExplorer -Name 'NoNetHood' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null

if ($account -and $account.SID) {
    $sid = $account.SID.Value
    $hkuExplorer = "Registry::HKEY_USERS\$sid\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    New-Item -Path $hkuExplorer -Force -ErrorAction SilentlyContinue | Out-Null
    Remove-ItemProperty -LiteralPath $hkuExplorer -Name 'NoViewOnDrive' -ErrorAction SilentlyContinue
    New-ItemProperty -LiteralPath $hkuExplorer -Name 'NoDrives' -PropertyType DWord -Value 67108863 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $hkuExplorer -Name 'NoNetHood' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $hkuExplorer -Name 'NoNavPane' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $hkuExplorer -Name 'NoSetFolders' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $hkuExplorer -Name 'NoFind' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
}

$ntuser = "C:\Users\$name\NTUSER.DAT"
if (Test-Path -LiteralPath $ntuser) {
    & reg.exe load "HKU\LR_USER_$name" "$ntuser" 2>&1 | Out-Null
    $tempExplorer = "Registry::HKEY_USERS\LR_USER_$name\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    New-Item -Path $tempExplorer -Force -ErrorAction SilentlyContinue | Out-Null
    Remove-ItemProperty -LiteralPath $tempExplorer -Name 'NoViewOnDrive' -ErrorAction SilentlyContinue
    New-ItemProperty -LiteralPath $tempExplorer -Name 'NoDrives' -PropertyType DWord -Value 67108863 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempExplorer -Name 'NoNetHood' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempExplorer -Name 'NoNavPane' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempExplorer -Name 'NoSetFolders' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempExplorer -Name 'NoFind' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    [GC]::Collect()
    & reg.exe unload "HKU\LR_USER_$name" 2>&1 | Out-Null
}

$defaultNtuser = 'C:\Users\Default\NTUSER.DAT'
if (Test-Path -LiteralPath $defaultNtuser) {
    & reg.exe load 'HKU\LR_DEFAULT_USER' "$defaultNtuser" 2>&1 | Out-Null
    $tempDefExplorer = 'Registry::HKEY_USERS\LR_DEFAULT_USER\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer'
    New-Item -Path $tempDefExplorer -Force -ErrorAction SilentlyContinue | Out-Null
    Remove-ItemProperty -LiteralPath $tempDefExplorer -Name 'NoViewOnDrive' -ErrorAction SilentlyContinue
    New-ItemProperty -LiteralPath $tempDefExplorer -Name 'NoDrives' -PropertyType DWord -Value 67108863 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempDefExplorer -Name 'NoNetHood' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempDefExplorer -Name 'NoNavPane' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempDefExplorer -Name 'NoSetFolders' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    New-ItemProperty -LiteralPath $tempDefExplorer -Name 'NoFind' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    [GC]::Collect()
    & reg.exe unload 'HKU\LR_DEFAULT_USER' 2>&1 | Out-Null
}

$computer = Get-CimInstance Win32_ComputerSystem
$isDomainController = [int]$computer.DomainRole -ge 4
$isDomainAccount = ([string]$account.PrincipalSource -eq 'ActiveDirectory') -or $isDomainController
$scope = if ($isDomainAccount) { 'domain' } else { 'local' }
$domain = ''
if ($isDomainAccount) {
    $ntDomain = Get-CimInstance Win32_NTDomain |
        Where-Object { $_.DnsForestName -ieq [string]$computer.Domain -or $_.Status -eq 'OK' } |
        Select-Object -First 1
    $domain = [string]$ntDomain.DomainName
    if (-not $domain) { $domain = [string]$env:USERDOMAIN }
    if (-not $domain) { $domain = [string]$computer.Domain }
}
[pscustomobject]@{
    scope = $scope
    domain = $domain
} | ConvertTo-Json -Compress
exit 0
"""
    script_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
            handle.write(script)
            script_path = handle.name

        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
                username,
                password,
                full_name,
                description,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        if script_path:
            try:
                Path(script_path).unlink(missing_ok=True)
            except OSError:
                pass
