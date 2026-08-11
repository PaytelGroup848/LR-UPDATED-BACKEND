[CmdletBinding(SupportsShouldProcess = $true)]
param()

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$currentPrincipal = [Security.Principal.WindowsPrincipal]::new($currentIdentity)
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window on the Windows RDP session host."
}

$terminalServicesPolicy = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services"
$winStations = "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations"

if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, "Enable GPU, WDDM, H.264/AVC and 60 FPS RDP policies")) {
    New-Item -Path $terminalServicesPolicy -Force | Out-Null

    # Microsoft policy mappings for hardware rendering and AVC encoding.
    New-ItemProperty -Path $terminalServicesPolicy -Name "bEnumerateHWBeforeSW" -PropertyType DWord -Value 1 -Force | Out-Null
    New-ItemProperty -Path $terminalServicesPolicy -Name "fEnableWddmDriver" -PropertyType DWord -Value 1 -Force | Out-Null
    New-ItemProperty -Path $terminalServicesPolicy -Name "AVCHardwareEncodePreferred" -PropertyType DWord -Value 1 -Force | Out-Null
    New-ItemProperty -Path $terminalServicesPolicy -Name "AVC444ModePreferred" -PropertyType DWord -Value 1 -Force | Out-Null

    # A value of 15 raises the RDP host ceiling from 30 FPS to 60 FPS. Actual
    # frame rate still depends on the GPU, CPU, network and Guacamole capacity.
    New-Item -Path $winStations -Force | Out-Null
    New-ItemProperty -Path $winStations -Name "DWMFRAMEINTERVAL" -PropertyType DWord -Value 15 -Force | Out-Null

    Write-Host "RDP video policies applied. Restart Windows before testing a new session."
}
