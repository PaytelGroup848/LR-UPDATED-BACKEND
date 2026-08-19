import platform
import re
import subprocess
import tempfile
import ntpath
from pathlib import Path
from datetime import datetime, timezone

from backend.extensions import db, socketio
from backend.core.config import settings
from backend.models.server import Server


def _clean_text(value):
    return str(value or "").strip()


def _username_leaf(username):
    value = _clean_text(username)
    if "\\" in value:
        value = value.rsplit("\\", 1)[-1]
    if "@" in value:
        value = value.split("@", 1)[0]
    return value


def _safe_name(value):
    name = re.sub(r'[\\/:*?"<>|]+', " ", _clean_text(value)).strip()
    return re.sub(r"\s+", " ", name) or "Application"


def _shortcut_spec(app):
    item_type = _clean_text(app.get("item_type"))
    display_mode = _clean_text(app.get("display_mode"))
    launch_mode = _clean_text(app.get("launch_mode"))
    target = _clean_text(app.get("target"))
    remote_app_program = _clean_text(app.get("remote_app_program"))
    remote_app_file_path = _clean_text(app.get("remote_app_file_path"))
    remote_app_source_file_path = _clean_text(app.get("remote_app_source_file_path"))
    initial_program = _clean_text(app.get("initial_program"))
    folder_path = _clean_text(app.get("folder_path"))
    folder_permission = _clean_text(app.get("folder_permission") or "read").lower()
    arguments = _clean_text(app.get("arguments"))
    working_directory = _clean_text(app.get("working_directory"))

    if item_type == "folder" or folder_path:
        return {
            "target_path": "explorer.exe",
            "arguments": folder_path or target or arguments,
            "working_directory": working_directory,
            "icon_path": "",
            "folder_permission": folder_permission,
        }, None

    target_path = (
        remote_app_source_file_path
        or remote_app_file_path
        or target
        or initial_program
        or remote_app_program
    )
    if not target_path and (item_type == "desktop" or display_mode == "full_desktop" or launch_mode == "desktop"):
        return None, "Full desktop assignments do not create app shortcuts."
    if target_path.startswith("||"):
        target_path = _safe_name(app.get("name"))
    if not target_path:
        target_path = _safe_name(app.get("name"))
    if working_directory.lower().endswith((".exe", ".bat", ".cmd", ".msi")):
        working_directory = ntpath.dirname(working_directory)

    return {
        "target_path": target_path,
        "arguments": arguments,
        "working_directory": working_directory or (ntpath.dirname(target_path) if "\\" in target_path else ""),
        "icon_path": target_path if target_path.lower().endswith(".exe") else "",
    }, None


def _job_filter(user, app, action):
    return {
        "tenant_id": (app or {}).get("tenant_id") or (user or {}).get("tenant_id"),
        "user_id": str((user or {}).get("_id") or (user or {}).get("id") or ""),
        "app_id": str((app or {}).get("_id") or (app or {}).get("id") or ""),
        "action": action,
    }


def _queue_shortcut_job(action, user, app, spec=None, reason=""):
    username = _username_leaf((user or {}).get("windows_username") or (user or {}).get("username"))
    shortcut_name = _safe_name((app or {}).get("name"))
    if not username or not shortcut_name:
        return {"success": False, "message": "Shortcut queue skipped: username or shortcut name is missing.", "skipped": True}

    job = {
        **_job_filter(user, app, action),
        "server_id": str((app or {}).get("server_id") or ""),
        "username": username,
        "shortcut_name": shortcut_name,
        "spec": spec or {},
        "reason": reason,
        "updated_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "attempts": 0,
    }
    db["desktop_shortcut_jobs"].update_one(
        _job_filter(user, app, action),
        {
            "$set": {key: value for key, value in job.items() if key != "created_at"},
            "$setOnInsert": {"created_at": job["created_at"]},
        },
        upsert=True,
    )
    return {"success": False, "message": reason or "Shortcut sync queued until Windows Agent is online.", "queued": True}


def _clear_shortcut_job(action, user, app):
    db["desktop_shortcut_jobs"].delete_one(_job_filter(user, app, action))


def _call_agent(agent_sid, event, payload, timeout=35):
    return socketio.call(event, payload, namespace="/agent", to=agent_sid, timeout=timeout)


def _agent_sid_for_app(app):
    try:
        from backend.sockets.agent_socket import connected_agents
    except Exception:
        return None

    tenant_id = app.get("tenant_id")
    server = Server.get_by_id(app.get("server_id"), tenant_id)
    server_host = _clean_text((server or {}).get("host")).lower()
    server_name = _clean_text(
        (server or {}).get("domain")
        or (server or {}).get("windows_domain")
        or (server or {}).get("hostname")
        or (server or {}).get("name")
    ).lower()

    fallback_sid = None
    for sid, info in connected_agents.items():
        if tenant_id is not None and str(info.get("tenant_id")) != str(tenant_id):
            continue
        os_name = _clean_text(info.get("os")).lower()
        if "windows" not in os_name and not os_name.startswith("win"):
            continue
        fallback_sid = fallback_sid or sid
        hostname = _clean_text(info.get("hostname")).lower()
        ip_address = _clean_text(info.get("ip_address")).lower()
        if server_name and hostname == server_name:
            return sid
        if server_host and ip_address == server_host:
            return sid
    return fallback_sid


def _run_local_shortcut_script(action, username, shortcut_name, spec):
    script = r"""param(
    [string]$action,
    [string]$username,
    [string]$shortcutName,
    [string]$targetPath,
    [string]$arguments,
    [string]$workingDirectory,
    [string]$iconPath,
    [string]$folderPermission
)
$ErrorActionPreference = 'Stop'
function Resolve-UserProfilePath {
    param([string]$UserName)
    $userLeaf = ($UserName -split '\\')[-1]
    $matches = @()
    $profileList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList'
    foreach ($profileKey in Get-ChildItem -LiteralPath $profileList -ErrorAction Stop) {
        try {
            $sidValue = $profileKey.PSChildName
            $sid = New-Object System.Security.Principal.SecurityIdentifier($sidValue)
            $account = $sid.Translate([System.Security.Principal.NTAccount]).Value
            if ((($account -split '\\')[-1]) -ine $userLeaf) { continue }
            $rawPath = (Get-ItemProperty -LiteralPath $profileKey.PSPath).ProfileImagePath
            $resolvedPath = [Environment]::ExpandEnvironmentVariables($rawPath)
            if ($resolvedPath -and (Test-Path -LiteralPath $resolvedPath -PathType Container)) {
                $matches += [pscustomobject]@{
                    Path = $resolvedPath
                    Loaded = Test-Path -LiteralPath ('Registry::HKEY_USERS\' + $sidValue)
                }
            }
        } catch {}
    }
    if ($matches.Count -eq 1) { return $matches[0].Path }
    $loaded = @($matches | Where-Object { $_.Loaded })
    if ($loaded.Count -eq 1) { return $loaded[0].Path }
    if ($matches.Count -eq 0) {
        throw ('Windows profile is not initialized for user ' + $UserName + '. Sign in once, then retry.')
    }
    throw ('Multiple Windows profiles match user ' + $UserName + '. Configure a domain-qualified username.')
}

$profilePath = Resolve-UserProfilePath -UserName $username
$profileDesktop = Join-Path $profilePath 'Desktop'
$publicDesktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
if (-not $publicDesktop) { $publicDesktop = 'C:\Users\Public\Desktop' }
if (-not $username) { throw 'Windows username is required.' }
if (-not (Test-Path -LiteralPath $profileDesktop)) {
    New-Item -ItemType Directory -Path $profileDesktop -Force | Out-Null
}
$shortcutPath = Join-Path $profileDesktop ($shortcutName + '.lnk')
$legacyShortcutPath = Join-Path $publicDesktop ($shortcutName + '.lnk')
function Grant-ShortcutMaintenanceAccess {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }

    & icacls.exe $Path /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' /C | Out-Null
    if ($LASTEXITCODE -eq 0) { return }

    & takeown.exe /F $Path /A | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw ('Unable to take ownership of managed shortcut ' + $Path)
    }
    & icacls.exe $Path /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' /C | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw ('Unable to repair managed shortcut permissions for ' + $Path)
    }
}
function Remove-PublicAppShortcut {
    param([string]$Name)
    if (-not $publicDesktop -or -not (Test-Path -LiteralPath $publicDesktop)) { return }
    $cleanName = ($Name -replace '[\\/:*?"<>|]+', ' ').Trim()
    $noSpaceName = ($cleanName -replace '\s+', '')
    foreach ($item in Get-ChildItem -LiteralPath $publicDesktop -Filter '*.lnk' -File -ErrorAction SilentlyContinue) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($item.Name)
        $cleanBase = ($baseName -replace '[\\/:*?"<>|]+', ' ').Trim()
        $noSpaceBase = ($cleanBase -replace '\s+', '')
        if ($cleanBase -eq $cleanName -or $noSpaceBase -eq $noSpaceName) {
            Grant-ShortcutMaintenanceAccess -Path $item.FullName
            Remove-Item -LiteralPath $item.FullName -Force -ErrorAction SilentlyContinue
        }
    }
}
if ($action -eq 'delete') {
    if (Test-Path -LiteralPath $shortcutPath) {
        Grant-ShortcutMaintenanceAccess -Path $shortcutPath
        Remove-Item -LiteralPath $shortcutPath -Force
    }
    if (Test-Path -LiteralPath $legacyShortcutPath) { Remove-Item -LiteralPath $legacyShortcutPath -Force }
    Remove-PublicAppShortcut -Name $shortcutName
    exit 0
}
Remove-PublicAppShortcut -Name $shortcutName
$targetPath = [Environment]::ExpandEnvironmentVariables($targetPath)
$workingDirectory = [Environment]::ExpandEnvironmentVariables($workingDirectory)
$iconPath = [Environment]::ExpandEnvironmentVariables($iconPath)
$folderPermission = $folderPermission.ToLowerInvariant()
function Resolve-AppTarget {
    param([string]$Target, [string]$UserName, [string]$ShortcutName)
    if (-not $Target) { return $Target }
    if ([System.IO.Path]::IsPathRooted($Target) -and (Test-Path -LiteralPath $Target)) {
        return (Resolve-Path -LiteralPath $Target).Path
    }

    $leaf = Split-Path -Leaf $Target
    if (-not $leaf) { $leaf = $Target }
    $rawNames = @($leaf, $ShortcutName) | Where-Object { $_ } | Select-Object -Unique
    $names = @()
    foreach ($rawName in $rawNames) {
        $names += $rawName
        if ([System.IO.Path]::GetExtension($rawName) -eq '') { $names += "$rawName.exe" }
        foreach ($part in ($rawName -split '\s+')) {
            if ($part.Length -gt 1) {
                $names += $part
                $names += "$part.exe"
            }
        }
    }
    $names = $names | Where-Object { $_ } | Select-Object -Unique

    foreach ($name in $names) {
        foreach ($registryPath in @(
            "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\$name",
            "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\$name",
            "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\$name"
        )) {
            $item = Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue
            if ($item -and $item.'(default)' -and (Test-Path -LiteralPath $item.'(default)')) {
                return (Resolve-Path -LiteralPath $item.'(default)').Path
            }
        }
    }

    $profilePath = Resolve-UserProfilePath -UserName $UserName
    $searchRoots = @(
        (Join-Path $profilePath 'AppData\Local'),
        (Join-Path $profilePath 'AppData\Roaming'),
        (Join-Path $profilePath 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs'),
        'C:\ProgramData\Microsoft\Windows\Start Menu\Programs',
        ${env:ProgramFiles},
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    $shell = New-Object -ComObject WScript.Shell
    function Normalize-Name([string]$Value) {
        return (($Value -replace '\.lnk$','' -replace '\.exe$','' -replace '[^a-zA-Z0-9]+','').ToLowerInvariant())
    }
    $normalizedNames = $names | ForEach-Object { Normalize-Name $_ } | Where-Object { $_ } | Select-Object -Unique
    foreach ($root in $searchRoots) {
        foreach ($name in $names) {
            $match = Get-ChildItem -LiteralPath $root -Filter $name -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($match) { return $match.FullName }
        }

        $shortcut = Get-ChildItem -LiteralPath $root -Filter '*.lnk' -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object {
                $base = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
                $normalizedBase = Normalize-Name $base
                $names -contains $_.Name -or
                    $names -contains $base -or
                    $base -eq [System.IO.Path]::GetFileNameWithoutExtension($leaf) -or
                    ($normalizedNames | Where-Object { $normalizedBase -eq $_ -or $normalizedBase.Contains($_) -or $_.Contains($normalizedBase) } | Select-Object -First 1)
            } |
            Select-Object -First 1
        if ($shortcut) {
            $resolvedShortcut = $shell.CreateShortcut($shortcut.FullName)
            if ($resolvedShortcut.TargetPath -and (Test-Path -LiteralPath $resolvedShortcut.TargetPath)) {
                return (Resolve-Path -LiteralPath $resolvedShortcut.TargetPath).Path
            }
        }
    }

    foreach ($name in $names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source)) {
            return (Resolve-Path -LiteralPath $command.Source).Path
        }
    }

    return $Target
}

$targetPath = Resolve-AppTarget -Target $targetPath -UserName $username -ShortcutName $shortcutName
if (-not (Test-Path -LiteralPath $targetPath) -and -not [System.IO.Path]::IsPathRooted($targetPath)) {
    throw "Shortcut target '$targetPath' was not found. Use a full executable path or install the app for user '$username'."
}
function Publish-SharedAppCopy {
    param([string]$ResolvedTarget, [string]$UserName, [string]$ShortcutName)
    if (-not (Test-Path -LiteralPath $ResolvedTarget)) { return $ResolvedTarget }

    $normalizedTarget = [System.IO.Path]::GetFullPath($ResolvedTarget)
    $targetUserRoot = [System.IO.Path]::GetFullPath((Resolve-UserProfilePath -UserName $UserName))
    if ($normalizedTarget.StartsWith($targetUserRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $ResolvedTarget
    }

    $profileMatch = [regex]::Match($normalizedTarget, '^C:\\Users\\([^\\]+)\\', 'IgnoreCase')
    if (-not $profileMatch.Success) { return $ResolvedTarget }

    $sourceDir = Split-Path -Parent $normalizedTarget
    $safeName = ($ShortcutName -replace '[\\/:*?"<>|]+', ' ').Trim()
    if (-not $safeName) { $safeName = [System.IO.Path]::GetFileNameWithoutExtension($ResolvedTarget) }
    $publishRoot = Join-Path $env:ProgramData 'LRPlatform\PublishedApps'
    $destinationDir = Join-Path $publishRoot $safeName
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceDir '*') -Destination $destinationDir -Recurse -Force -ErrorAction SilentlyContinue
    & icacls $destinationDir /grant 'Users:(OI)(CI)RX' /T /C | Out-Null
    $publishedTarget = Join-Path $destinationDir (Split-Path -Leaf $ResolvedTarget)
    if (Test-Path -LiteralPath $publishedTarget) { return $publishedTarget }
    return $ResolvedTarget
}

$sourceTargetPath = $targetPath
$sourceWorkingDirectory = Split-Path -Parent $sourceTargetPath
$targetPath = Publish-SharedAppCopy -ResolvedTarget $targetPath -UserName $username -ShortcutName $shortcutName
if (-not [string]::Equals($targetPath, $sourceTargetPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    if (-not $workingDirectory -or [string]::Equals($workingDirectory.TrimEnd('\'), $sourceWorkingDirectory.TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)) {
        $workingDirectory = Split-Path -Parent $targetPath
    }
    if (-not $iconPath -or [string]::Equals($iconPath, $sourceTargetPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        $iconPath = $targetPath
    }
}
$isFolderShortcut = $targetPath.ToLowerInvariant().EndsWith('explorer.exe') -and $arguments
$folderPathForAcl = $arguments.Trim('"')
if (-not $workingDirectory -and (Test-Path -LiteralPath $targetPath)) { $workingDirectory = Split-Path -Parent $targetPath }
if (-not $iconPath -and $targetPath.ToLower().EndsWith('.exe') -and (Test-Path -LiteralPath $targetPath)) { $iconPath = $targetPath }
$shortcutArguments = $arguments
if ($isFolderShortcut -and $folderPathForAcl -and -not ($shortcutArguments.StartsWith('"') -and $shortcutArguments.EndsWith('"'))) {
    $shortcutArguments = '"' + $folderPathForAcl + '"'
}
Grant-ShortcutMaintenanceAccess -Path $shortcutPath
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
if ($shortcutArguments) { $shortcut.Arguments = $shortcutArguments }
if ($workingDirectory) { $shortcut.WorkingDirectory = $workingDirectory }
if ($iconPath) { $shortcut.IconLocation = $iconPath }
$shortcut.Save()
try {
    $acl = Get-Acl -LiteralPath $shortcutPath
    $acl.SetAccessRuleProtection($true, $false)
    $acl.Access | ForEach-Object { [void]$acl.RemoveAccessRule($_) }
    $rights = [System.Security.AccessControl.FileSystemRights]'ReadAndExecute'
    $inheritance = [System.Security.AccessControl.InheritanceFlags]'None'
    $propagation = [System.Security.AccessControl.PropagationFlags]'None'
    $allow = [System.Security.AccessControl.AccessControlType]'Allow'
    foreach ($identity in @($username, "$env:COMPUTERNAME\$username", 'Administrators', 'SYSTEM')) {
        try {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, $rights, $inheritance, $propagation, $allow)
            $acl.AddAccessRule($rule)
        } catch {}
    }
    $privilegedRights = [System.Security.AccessControl.FileSystemRights]'FullControl'
    foreach ($identity in @('Administrators', 'SYSTEM')) {
        try {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, $privilegedRights, $inheritance, $propagation, $allow)
            $acl.AddAccessRule($rule)
        } catch {}
    }
    Set-Acl -LiteralPath $shortcutPath -AclObject $acl
} catch {
    Write-Warning "Shortcut was created but per-user ACL could not be applied: $($_.Exception.Message)"
}
if ($isFolderShortcut -and $folderPathForAcl -and (Test-Path -LiteralPath $folderPathForAcl -PathType Container)) {
    $grant = if ($folderPermission -eq 'write') { 'M' } else { 'RX' }
    & icacls $folderPathForAcl /grant "$username`:(OI)(CI)$grant" /C | Out-Null
}
exit 0
"""
    script_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
            handle.write(script)
            script_path = handle.name
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
                action,
                username,
                shortcut_name,
                (spec or {}).get("target_path", ""),
                (spec or {}).get("arguments", ""),
                (spec or {}).get("working_directory", ""),
                (spec or {}).get("icon_path", ""),
                (spec or {}).get("folder_permission", ""),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    finally:
        if script_path:
            try:
                Path(script_path).unlink(missing_ok=True)
            except OSError:
                pass

    if result.returncode == 0:
        return {"success": True, "message": "Desktop shortcut synced locally"}
    return {
        "success": False,
        "message": (result.stderr or result.stdout or "PowerShell returned an error").strip(),
    }


class DesktopShortcutService:
    @staticmethod
    def sync_assignment_shortcut(user, app):
        username = _username_leaf(
            (user or {}).get("windows_username")
            or (user or {}).get("username")
        )
        shortcut_name = _safe_name((app or {}).get("name"))
        spec, error = _shortcut_spec(app or {})
        if error:
            return {"success": False, "message": error, "skipped": True}
        spec = spec or {}

        agent_sid = _agent_sid_for_app(app or {})
        if agent_sid:
            payload = {
                "tenant_id": str((app or {}).get("tenant_id") or ""),
                "username": username,
                "shortcut_name": shortcut_name,
                **spec,
            }
            try:
                result = _call_agent(agent_sid, "create_desktop_shortcut", payload)
                if result and result.get("success"):
                    _clear_shortcut_job("create", user, app)
                    return result
                return _queue_shortcut_job(
                    "create",
                    user,
                    app,
                    spec,
                    (result or {}).get("message") or "Windows Agent did not create shortcut.",
                )
            except Exception as error:
                return _queue_shortcut_job(
                    "create",
                    user,
                    app,
                    spec,
                    f"Windows Agent did not create shortcut: {error}",
                )

        if settings.ALLOW_LEGACY_LOCAL_HOST_OPERATIONS and platform.system().lower() == "windows":
            result = _run_local_shortcut_script("create", username, shortcut_name, spec)
            if result.get("success"):
                _clear_shortcut_job("create", user, app)
            return result

        return _queue_shortcut_job(
            "create",
            user,
            app,
            spec,
            "No connected Windows Agent found for shortcut sync.",
        )

    @staticmethod
    def remove_assignment_shortcut(user, app):
        username = _username_leaf(
            (user or {}).get("windows_username")
            or (user or {}).get("username")
        )
        shortcut_name = _safe_name((app or {}).get("name"))
        if not username:
            return {"success": False, "message": "Windows username is required."}

        agent_sid = _agent_sid_for_app(app or {})
        if agent_sid:
            try:
                result = _call_agent(
                    agent_sid,
                    "delete_desktop_shortcut",
                    {"username": username, "shortcut_name": shortcut_name},
                )
                if result and result.get("success"):
                    _clear_shortcut_job("delete", user, app)
                    return result
                return _queue_shortcut_job(
                    "delete",
                    user,
                    app,
                    {},
                    (result or {}).get("message") or "Windows Agent did not delete shortcut.",
                )
            except Exception as error:
                return _queue_shortcut_job(
                    "delete",
                    user,
                    app,
                    {},
                    f"Windows Agent did not delete shortcut: {error}",
                )

        if settings.ALLOW_LEGACY_LOCAL_HOST_OPERATIONS and platform.system().lower() == "windows":
            result = _run_local_shortcut_script("delete", username, shortcut_name, {})
            if result.get("success"):
                _clear_shortcut_job("delete", user, app)
            return result

        return _queue_shortcut_job(
            "delete",
            user,
            app,
            {},
            "No connected Windows Agent found for shortcut sync.",
        )

    @staticmethod
    def sync_pending_for_agent(agent_sid=None, reconcile_assignments=True):
        if platform.system().lower() == "windows":
            return {"success": True, "processed": 0}

        processed = 0
        for job in db["desktop_shortcut_jobs"].find().sort("updated_at", 1):
            app = {"server_id": job.get("server_id"), "name": job.get("shortcut_name")}
            matched_sid = _agent_sid_for_app(app)
            if agent_sid and matched_sid != agent_sid:
                continue
            if not matched_sid:
                continue

            action = job.get("action")
            payload = {
                "username": job.get("username"),
                "shortcut_name": job.get("shortcut_name"),
                **(job.get("spec") or {}),
            }
            event = "delete_desktop_shortcut" if action == "delete" else "create_desktop_shortcut"
            try:
                result = _call_agent(matched_sid, event, payload)
            except Exception as error:
                db["desktop_shortcut_jobs"].update_one(
                    {"_id": job["_id"]},
                    {"$set": {"reason": str(error), "updated_at": datetime.now(timezone.utc)}, "$inc": {"attempts": 1}},
                )
                continue

            if result and result.get("success"):
                db["desktop_shortcut_jobs"].delete_one({"_id": job["_id"]})
                processed += 1
            else:
                db["desktop_shortcut_jobs"].update_one(
                    {"_id": job["_id"]},
                    {
                        "$set": {
                            "reason": (result or {}).get("message") or "Shortcut sync failed.",
                            "updated_at": datetime.now(timezone.utc),
                        },
                        "$inc": {"attempts": 1},
                    },
                )

        if not reconcile_assignments:
            return {"success": True, "processed": processed}

        try:
            from backend.models.application import PublishedApp
            from backend.models.assignment import ApplicationAssignment
            from backend.models.user import User

            for assignment in ApplicationAssignment.collection.find({"is_enabled": True}):
                app = PublishedApp.get_by_id(assignment.get("app_id"))
                user = User.get_by_id(assignment.get("user_id"))
                if not app or not user:
                    continue
                matched_sid = _agent_sid_for_app(app)
                if agent_sid and matched_sid != agent_sid:
                    continue
                if not matched_sid:
                    continue
                result = DesktopShortcutService.sync_assignment_shortcut(user, app)
                if result and result.get("success"):
                    processed += 1
        except Exception:
            pass

        return {"success": True, "processed": processed}
