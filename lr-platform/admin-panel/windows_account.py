import json
import platform
import re
import subprocess
import tempfile
from pathlib import Path


INVALID_USERNAME_CHARS = re.compile(r'[\\/"\[\]:;|=,+*?<>@]')
MANAGED_ACCOUNT_DESCRIPTION = "LR Remote published-app user"


def _clean_text(value):
    return str(value or "").strip()


def create_windows_user(username, password, full_name="", description=""):
    username = _clean_text(username)
    password = str(password or "")

    if platform.system().lower() != "windows":
        return False, "Windows account creation must run on Windows."

    if not username or not password:
        return False, "Windows username and password are required."

    if len(username) > 20 or INVALID_USERNAME_CHARS.search(username) or username.endswith("."):
        return False, "Windows username is invalid. Use 1-20 characters without special Windows account symbols."

    result = _run_account_script(
        username=username,
        password=password,
        full_name=full_name or username,
        description=description or "LR Remote published-app user",
    )

    if result.returncode == 0:
        return True, "Windows account created"
    if result.returncode == 10:
        return False, "Windows username already exists"

    detail = (result.stderr or result.stdout or "").strip()
    if "InvalidPasswordException" in detail or "FullyQualifiedErrorId : InvalidPassword" in detail:
        return False, (
            "Windows rejected this password. Use a stronger password that meets the local Windows policy, "
            "for example 8+ characters with uppercase, lowercase, number, and symbol."
        )
    return False, f"Windows account creation failed: {detail or 'PowerShell returned an error'}"


def resolve_windows_account_identity(username):
    username = _clean_text(username)
    if platform.system().lower() != "windows" or not username:
        return {}

    try:
        result = _run_identity_script(username)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}

    try:
        identity = json.loads((result.stdout or "").strip())
    except (TypeError, ValueError):
        return {}

    scope = _clean_text(identity.get("scope")).lower()
    if scope not in {"local", "domain"}:
        return {}
    return {
        "scope": scope,
        "domain": _clean_text(identity.get("domain")) if scope == "domain" else "",
    }


def delete_windows_user(username):
    username = _clean_text(username)

    if platform.system().lower() != "windows":
        return False, "Windows account deletion must run on Windows."

    if not username:
        return False, "Windows username is required."

    if len(username) > 20 or INVALID_USERNAME_CHARS.search(username) or username.endswith("."):
        return False, "Windows username is invalid."

    try:
        result = _run_delete_script(username, MANAGED_ACCOUNT_DESCRIPTION)
    except subprocess.TimeoutExpired:
        return False, "Windows account deletion timed out."
    except OSError as error:
        return False, f"Windows account deletion failed: {error}"

    if result.returncode == 0:
        return True, "Windows account deleted"
    if result.returncode == 11:
        return True, "Windows account was already absent"
    if result.returncode == 12:
        return False, "Protected Windows system accounts cannot be deleted."
    if result.returncode == 13:
        return False, (
            "This Windows account was not created by LR Remote Access, so it was not deleted. "
            "Remove it manually if it is safe to do so."
        )

    detail = (result.stderr or result.stdout or "").strip()
    return False, f"Windows account deletion failed: {detail or 'PowerShell returned an error'}"


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


def _run_delete_script(username, expected_description):
    script = """param(
    [string]$name,
    [string]$expectedDescription
)
$ErrorActionPreference = 'Stop'
$account = Get-LocalUser -Name $name -ErrorAction SilentlyContinue
if (-not $account) { exit 11 }
$sid = [string]$account.SID
if ($sid -match '-(500|501|503|504)$') { exit 12 }
if ([string]$account.Description -ne $expectedDescription) { exit 13 }
Remove-LocalUser -Name $name
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
                expected_description,
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


def _run_identity_script(username):
    script = """param([string]$name)
$ErrorActionPreference = 'Stop'
$account = Get-LocalUser -Name $name -ErrorAction SilentlyContinue
if (-not $account) { exit 11 }
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
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    finally:
        if script_path:
            try:
                Path(script_path).unlink(missing_ok=True)
            except OSError:
                pass
