import getpass
import platform
import subprocess

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows import guard
    winreg = None


POLICY_MAP = {
    "system_disable_cmd": ("hkcu", r"Software\Policies\Microsoft\Windows\System", "DisableCMD", 1),
    "system_disable_registry": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\System", "DisableRegistryTools", 1),
    "system_disable_task_manager": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\System", "DisableTaskMgr", 1),
    "system_disable_control_panel": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoControlPanel", 1),
    "system_disable_settings": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoControlPanel", 1),
    "explorer_disable_usb": ("hklm", r"SYSTEM\CurrentControlSet\Services\USBSTOR", "Start", 4),
    "explorer_read_only_usb": ("hklm", r"SYSTEM\CurrentControlSet\Control\StorageDevicePolicies", "WriteProtect", 1),
    "explorer_hide_c_drive": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoDrives", 4),
    "explorer_hide_d_drive": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoDrives", 8),
    "desktop_disable_right_click": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoViewContextMenu", 1),
    "desktop_hide_desktop_icons": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "HideIcons", 1),
    "desktop_lock_wallpaper": ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Policies\ActiveDesktop", "NoChangingWallPaper", 1),
    "browser_disable_incognito": ("hkcu", r"Software\Policies\Google\Chrome", "IncognitoModeAvailability", 1),
    "browser_block_downloads": ("hkcu", r"Software\Policies\Google\Chrome", "DownloadRestrictions", 3),
}

DISALLOW_RUN_KEYS = {
    "system_disable_powershell": ["powershell.exe", "pwsh.exe"],
    "applications_block_software_install": ["msiexec.exe", "setup.exe", "install.exe"],
    "applications_block_exe_files": ["*.exe"],
    "applications_block_games": ["game.exe", "steam.exe", "epicgameslauncher.exe"],
}

UNSUPPORTED = {
    "desktop_prevent_delete": "No reliable Windows policy exists for generic desktop delete prevention.",
    "desktop_prevent_rename": "No reliable Windows policy exists for generic desktop rename prevention.",
    "desktop_prevent_create": "No reliable Windows policy exists for generic desktop create prevention.",
    "explorer_block_copy": "Clipboard/copy blocking requires a foreground/session hook; not implemented in this agent.",
    "explorer_block_paste": "Clipboard/paste blocking requires a foreground/session hook; not implemented in this agent.",
    "applications_allow_assigned_apps_only": "Assigned-app-only enforcement requires a launcher allowlist integration.",
    "browser_website_filtering": "Website filtering requires a URL filter/proxy or browser extension integration.",
}


def apply_policy(policy, target_username=None):
    if platform.system().lower() != "windows":
        return {
            "success": False,
            "message": "Windows policy enforcement is only supported on Windows agents.",
            "results": {},
        }

    current_user = getpass.getuser()
    if target_username and str(target_username).lower() not in {current_user.lower(), f".\\{current_user.lower()}"}:
        return {
            "success": False,
            "message": f"Agent is running as {current_user}; target user is {target_username}. Start the agent in the target user's Windows session.",
            "results": {},
        }

    results = {}
    policy = policy or {}
    for key, enabled in policy.items():
        if key in UNSUPPORTED:
            results[key] = {"success": not enabled, "message": "Not enabled" if not enabled else UNSUPPORTED[key]}
            continue
        if key in POLICY_MAP:
            results[key] = _apply_registry_policy(key, bool(enabled), policy)
            continue
        if key in DISALLOW_RUN_KEYS:
            results[key] = _apply_disallow_run(key, bool(enabled))
            continue
        results[key] = {"success": False, "message": "Unknown policy key"}

    _refresh_explorer_policy()
    overall = all(result.get("success") for result in results.values()) if results else True
    return {
        "success": overall,
        "message": "Policy enforcement completed" if overall else "Policy enforcement completed with warnings",
        "results": results,
    }


def _root(root_name):
    if root_name == "hkcu":
        return winreg.HKEY_CURRENT_USER
    return winreg.HKEY_LOCAL_MACHINE


def _apply_registry_policy(key, enabled, policy):
    if winreg is None:
        return {"success": False, "message": "winreg is not available"}

    root_name, path, value_name, enabled_value = POLICY_MAP[key]
    try:
        if value_name == "NoDrives":
            c_value = 4 if policy.get("explorer_hide_c_drive") else 0
            d_value = 8 if policy.get("explorer_hide_d_drive") else 0
            value = c_value | d_value
            _set_or_delete(root_name, path, value_name, value, delete=(value == 0))
        else:
            _set_or_delete(root_name, path, value_name, enabled_value, delete=not enabled)
        return {"success": True, "message": "Applied" if enabled else "Removed"}
    except PermissionError:
        return {"success": False, "message": "Permission denied. Run agent as administrator for this policy."}
    except OSError as error:
        return {"success": False, "message": str(error)}


def _set_or_delete(root_name, path, name, value, delete=False):
    access = winreg.KEY_SET_VALUE
    root = _root(root_name)
    if delete:
        try:
            with winreg.OpenKey(root, path, 0, access) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        return
    with winreg.CreateKeyEx(root, path, 0, access) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))


def _apply_disallow_run(policy_key, enabled):
    if winreg is None:
        return {"success": False, "message": "winreg is not available"}
    path = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    list_path = path + r"\DisallowRun"
    try:
        if not enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, "DisallowRun")
            return {"success": True, "message": "Removed"}
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisallowRun", 0, winreg.REG_DWORD, 1)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, list_path, 0, winreg.KEY_SET_VALUE) as key:
            for index, exe_name in enumerate(DISALLOW_RUN_KEYS[policy_key], start=1):
                winreg.SetValueEx(key, str(index), 0, winreg.REG_SZ, exe_name)
        return {"success": True, "message": "Applied"}
    except FileNotFoundError:
        return {"success": True, "message": "Removed"}
    except PermissionError:
        return {"success": False, "message": "Permission denied"}
    except OSError as error:
        return {"success": False, "message": str(error)}


def _refresh_explorer_policy():
    try:
        subprocess.run(["gpupdate", "/target:user", "/force"], capture_output=True, timeout=30, check=False)
    except Exception:
        pass
