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
    script = """param(
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
