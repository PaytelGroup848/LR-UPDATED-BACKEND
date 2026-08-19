"""Module for automatic Windows RDS RemoteApp infrastructure detection and provisioning.

Ensures that missing RDS roles (RDS-RD-Server, RDS-Connection-Broker, RDS-Web-Access, RSAT-RDS-Tools),
RDS session deployment, and RDS session collections are automatically installed and configured
on customer servers prior to RemoteApp publication.
"""

RDS_PROVISIONER_SCRIPT = r'''
function Ensure-LRRDSInfrastructure {
    param(
        [string]$RequestedCollection,
        [string]$ConnectionBroker
    )

    $isServerOS = $false
    try {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue
        if (-not $os) {
            $os = Get-WmiObject -Class Win32_OperatingSystem -ErrorAction SilentlyContinue
        }
        if ($os -and ($os.ProductType -eq 2 -or $os.ProductType -eq 3)) {
            $isServerOS = $true
        }
    } catch {}

    if (-not $isServerOS) {
        return 'STANDALONE_CLIENT'
    }

    $rdsFeatures = @('RDS-RD-Server', 'RDS-Connection-Broker', 'RDS-Web-Access', 'RSAT-RDS-Tools')
    $missingFeatures = @()
    foreach ($feature in $rdsFeatures) {
        try {
            $state = Get-WindowsFeature -Name $feature -ErrorAction SilentlyContinue
            if ($state -and -not $state.Installed) {
                $missingFeatures += $feature
            }
        } catch {}
    }

    if ($missingFeatures.Count -gt 0) {
        try {
            $installResult = Install-WindowsFeature -Name $missingFeatures -IncludeManagementTools -ErrorAction Stop
            if ($installResult.RestartNeeded -eq 'Yes') {
                try { Restart-Computer -Force -ErrorAction SilentlyContinue } catch {}
                throw "RDS feature installation requires a server restart. Reboot initiated on $env:COMPUTERNAME."
            }
        } catch {
            if ($_.Exception.Message -like "*requires a server restart*" -or $_.Exception.Message -like "*reboot*") {
                throw
            }
            throw "Failed to install required RDS features ($($missingFeatures -join ', ')): $($_.Exception.Message)"
        }
    }

    Import-Module ServerManager -ErrorAction SilentlyContinue
    try {
        Import-Module RemoteDesktop -ErrorAction Stop
    } catch {
        $rebootPending = $false
        try {
            if (Test-Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') {
                $rebootPending = $true
            }
        } catch {}
        if ($rebootPending) {
            try { Restart-Computer -Force -ErrorAction SilentlyContinue } catch {}
            throw "Server reboot pending to register RemoteDesktop module. Reboot initiated on $env:COMPUTERNAME."
        }
        throw "RemoteDesktop PowerShell module is not available on $env:COMPUTERNAME. Ensure RSAT-RDS-Tools feature is installed and server is restarted."
    }

    foreach ($svcName in @('TermService', 'SessionEnv', 'UmRdpService', 'tssdis')) {
        try {
            $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
            if ($svc) {
                if ($svc.StartType -eq 'Disabled') {
                    Set-Service -Name $svcName -StartupType Automatic -ErrorAction SilentlyContinue
                }
                if ($svc.Status -ne 'Running') {
                    Start-Service -Name $svcName -ErrorAction SilentlyContinue
                }
            }
        } catch {}
    }

    $lookup = @{}
    Add-BrokerArgument -Arguments $lookup -ConnectionBroker $ConnectionBroker
    $hasDeployment = $false
    try {
        $dep = Get-RDDeployment @lookup -ErrorAction Stop
        if ($dep) { $hasDeployment = $true }
    } catch {}

    if (-not $hasDeployment) {
        try {
            $dep = Get-RDDeployment -ErrorAction Stop
            if ($dep) { $hasDeployment = $true }
        } catch {}
    }

    $serverName = $env:COMPUTERNAME
    if (-not $hasDeployment) {
        try {
            New-RDSessionDeployment -ConnectionBroker $serverName -WebAccessServer $serverName -SessionHost $serverName -ErrorAction Stop | Out-Null
            $hasDeployment = $true
        } catch {
            try {
                $dep = Get-RDDeployment -ErrorAction Stop
                if ($dep) { $hasDeployment = $true }
            } catch {
                return 'STANDALONE_SERVER'
            }
        }
    }

    $collectionName = ''
    $collections = @()
    try {
        $collections = @(Get-RDSessionCollection @lookup -ErrorAction Stop)
    } catch {
        try {
            $collections = @(Get-RDSessionCollection -ErrorAction Stop)
        } catch {}
    }

    $targetColl = if ($RequestedCollection) { $RequestedCollection } else { 'QuickSessionCollection' }
    $found = $collections | Where-Object { [string]$_.CollectionName -eq $targetColl } | Select-Object -First 1
    if ($found) {
        $collectionName = $targetColl
    } else {
        try {
            New-RDSessionCollection -CollectionName $targetColl -SessionHost $serverName -ConnectionBroker $serverName -ErrorAction Stop | Out-Null
            $collectionName = $targetColl
        } catch {
            $collections = @(Get-RDSessionCollection -ErrorAction SilentlyContinue)
            $foundAfter = $collections | Where-Object { [string]$_.CollectionName -eq $targetColl } | Select-Object -First 1
            if ($foundAfter) {
                $collectionName = $targetColl
            } else {
                return 'STANDALONE_SERVER'
            }
        }
    }

    $verifiedCollection = Get-RDSessionCollection | Where-Object { [string]$_.CollectionName -eq $collectionName } | Select-Object -First 1
    if (-not $verifiedCollection) {
        throw "RDS Session Collection '$collectionName' could not be verified via Get-RDSessionCollection on $serverName."
    }

    try {
        $rootPath = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList'
        New-Item -Path $rootPath -Force -ErrorAction SilentlyContinue | Out-Null
        New-ItemProperty -LiteralPath $rootPath -Name 'fDisabledAllowList' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
        New-ItemProperty -LiteralPath $rootPath -Name 'fAllowNonListWithShell' -PropertyType DWord -Value 1 -Force -ErrorAction SilentlyContinue | Out-Null
    } catch {}

    return $collectionName
}
'''
