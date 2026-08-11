import json
import platform
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from backend.extensions import socketio
from backend.core.config import settings
from backend.security.credential_crypto import encrypt_secret


class WindowsAccountService:
    ACCOUNT_SCOPES = {"local", "domain"}

    INVALID_USERNAME_CHARS = re.compile(r'[\\/"\[\]:;|=,+*?<>@]')

    @staticmethod
    def clean_text(value):
        return str(value or "").strip()

    @staticmethod
    def normalize_bool(value, default=True):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"false", "0", "no", "off"}

    @classmethod
    def normalize_scope(cls, value, *, create_local_account=False, domain=""):
        scope = cls.clean_text(value).lower()
        if scope in cls.ACCOUNT_SCOPES:
            return scope
        if create_local_account:
            return "local"
        return "domain" if cls.clean_text(domain) else None

    @classmethod
    def created_account_identity(cls, output):
        for line in reversed(str(output or "").splitlines()):
            try:
                data = json.loads(line.strip())
            except (TypeError, ValueError):
                continue
            scope = cls.normalize_scope(data.get("scope"), domain=data.get("domain"))
            if scope:
                return {
                    "windows_account_scope": scope,
                    "windows_domain": (
                        cls.clean_text(data.get("domain"))
                        if scope == "domain"
                        else None
                    ),
                }
        return {}

    @classmethod
    def build_updates(
        cls,
        data,
        default_username,
        default_password,
        create_local_account=True,
    ):
        enabled = cls.normalize_bool(data.get("windows_account_enabled"), True)
        if not enabled:
            return {
                "windows_account_enabled": False,
                "windows_username": None,
                "windows_domain": None,
                "windows_account_scope": None,
                "windows_password": None,
            }, None

        username = (
            cls.clean_text(data.get("windows_username"))
            or cls.clean_text(data.get("rdp_username"))
            or cls.clean_text(default_username)
        )
        password = (
            str(data.get("windows_password") or "")
            or str(data.get("rdp_password") or "")
            or str(default_password or "")
        )
        domain = cls.clean_text(data.get("windows_domain")) or cls.clean_text(data.get("rdp_domain"))
        scope = cls.normalize_scope(
            data.get("windows_account_scope"),
            create_local_account=create_local_account,
            domain=domain,
        )

        if scope == "local":
            domain = ""

        if not username or not password:
            return None, "Windows username and password are required"

        if create_local_account:
            provision = cls.create_local_user(
                username=username,
                password=password,
                full_name=cls.clean_text(data.get("full_name")) or username,
                description="LR Remote published-app user",
                domain=domain,
                tenant_id=data.get("_tenant_id"),
                server_id=data.get("windows_server_id") or data.get("server_id"),
                agent_id=data.get("windows_agent_id") or data.get("agent_id"),
            )
            if not provision["success"]:
                return None, provision["message"]
            provision_scope = cls.normalize_scope(
                provision.get("windows_account_scope"),
                domain=provision.get("windows_domain"),
            )
            if provision_scope:
                scope = provision_scope
                domain = (
                    cls.clean_text(provision.get("windows_domain"))
                    if scope == "domain"
                    else ""
                )

        return {
            "windows_username": username,
            "windows_domain": domain or None,
            "windows_account_scope": scope,
            "windows_password": encrypt_secret(password),
            "windows_account_enabled": True,
            "windows_account_provisioned": bool(create_local_account),
            "windows_account_provisioned_at": datetime.utcnow() if create_local_account else None,
        }, None

    @classmethod
    def create_local_user(
        cls, username, password, full_name="", description="", domain="",
        tenant_id=None, server_id=None, agent_id=None,
    ):
        username = cls.clean_text(username)
        domain = cls.clean_text(domain)

        if domain or "\\" in username:
            return {
                "success": False,
                "message": "Domain Windows accounts cannot be created locally. Use a local username without DOMAIN\\.",
            }

        if len(username) > 20 or cls.INVALID_USERNAME_CHARS.search(username) or username.endswith("."):
            return {
                "success": False,
                "message": "Windows username is invalid. Use 1-20 characters without special Windows account symbols.",
            }

        if not settings.ALLOW_LEGACY_LOCAL_HOST_OPERATIONS:
            return cls.create_via_agent(
                username, password, full_name, description,
                agent_id=agent_id, tenant_id=tenant_id, server_id=server_id,
            )

        if platform.system().lower() != "windows":
            return cls.create_via_agent(
                username, password, full_name, description,
                agent_id=agent_id, tenant_id=tenant_id, server_id=server_id,
            )

        result = cls.run_account_script(username, password, full_name or username, description)

        if result.returncode == 0:
            return {
                "success": True,
                "message": "Windows account created",
                **cls.created_account_identity(result.stdout),
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
        agent_result = cls.create_via_agent(
            username, password, full_name, description,
            agent_id=agent_id, tenant_id=tenant_id, server_id=server_id,
        )
        if agent_result.get("success"):
            return agent_result

        agent_message = agent_result.get("message")
        if agent_message:
            detail = f"{detail or 'PowerShell returned an error'} Agent fallback: {agent_message}"

        return {
            "success": False,
            "message": f"Windows account creation failed: {detail or 'PowerShell returned an error'}",
        }

    @staticmethod
    def run_account_script(username, password, full_name, description):
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

    @classmethod
    def create_via_agent(
        cls, username, password, full_name="", description="",
        agent_id=None, tenant_id=None, server_id=None,
    ):
        if not tenant_id or not server_id:
            return {
                "success": False,
                "message": "A tenant and selected Windows server are required for Agent routing.",
            }

        from backend.services.agent_command_service import AgentCommandService

        result = AgentCommandService.call_server(
            "create_windows_user",
            {
                "agent_id": agent_id,
                "tenant_id": str(tenant_id),
                "server_id": str(server_id),
                "username": username,
                "password": password,
                "full_name": full_name or username,
                "description": description,
            },
            tenant_id=tenant_id,
            server_id=server_id,
            timeout=35,
        )

        if isinstance(result, dict):
            return result

        return {
            "success": False,
            "message": "Windows Agent returned an invalid account creation response.",
        }
