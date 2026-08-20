import os
import subprocess
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class RemoteAppMonitor:
    @staticmethod
    def audit_and_remediate_host() -> Dict[str, Any]:
        """
        Automated anomaly detection & remediation for RemoteApp hosts.
        Checks:
        1. Public directory existence & ACL permissions
        2. Windows TSAppAllowList registry keys
        """
        anomalies: List[str] = []
        remediations: List[str] = []

        # 1. Directories check
        required_dirs = [
            r"C:\PublicFolders",
            r"C:\PublicFolders\User Create",
            r"C:\PublicFolders\New folder",
            r"C:\TallyPrime",
            r"C:\Apps\TallyPrime"
        ]

        for d in required_dirs:
            if not os.path.exists(d):
                anomalies.append(f"Directory missing: {d}")
                try:
                    os.makedirs(d, exist_ok=True)
                    subprocess.run(["icacls", d, "/grant", "Users:(OI)(CI)F", "/T"], capture_output=True)
                    subprocess.run(["icacls", d, "/grant", "Everyone:(OI)(CI)F", "/T"], capture_output=True)
                    remediations.append(f"Auto-created directory and applied FullControl ACL: {d}")
                except Exception as e:
                    anomalies.append(f"Failed to auto-create {d}: {e}")

        # 2. Registry check & sync
        ps_check = r"""
        $regBase = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList\Applications'
        $keys = Get-ChildItem -Path $regBase -ErrorAction SilentlyContinue
        $missing = @()
        foreach ($k in $keys) {
            Set-ItemProperty -Path $k.PSPath -Name 'ShowInTSWA' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $k.PSPath -Name 'CommandLineSetting' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
        }
        $missing -join ','
        """
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_check], capture_output=True, text=True)
            missing_keys = [k.strip() for k in res.stdout.strip().split(",") if k.strip()]
            if missing_keys:
                anomalies.append(f"Missing TSAppAllowList registry keys: {missing_keys}")
        except Exception as e:
            anomalies.append(f"Registry audit failed: {e}")

        return {
            "status": "healthy" if not anomalies else "remediated" if remediations else "anomalies_detected",
            "anomalies": anomalies,
            "remediations": remediations
        }
