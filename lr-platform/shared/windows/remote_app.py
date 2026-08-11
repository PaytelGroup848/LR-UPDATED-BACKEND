import base64
import json
import platform
import subprocess
import tempfile
from pathlib import Path


_REMOTE_APP_SCRIPT = r'''param([string]$PayloadBase64)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-LRResult {
    param([hashtable]$Result, [int]$ExitCode = 0)
    $Result | ConvertTo-Json -Compress -Depth 6
    exit $ExitCode
}

function Test-LRIsLocalHost {
    param([string]$ServerName)

    if (-not $ServerName) { return $true }
    $name = $ServerName.Trim().ToLowerInvariant()
    if ($name -in @('localhost', '127.0.0.1', '::1', '.')) { return $true }
    $shortName = $name.Split('.')[0]
    $localShort = $env:COMPUTERNAME.Trim().ToLowerInvariant().Split('.')[0]
    if ($shortName -eq $localShort) { return $true }
    $localNames = @($env:COMPUTERNAME)
    try {
        $hostEntry = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME)
        if ($hostEntry.HostName) { $localNames += $hostEntry.HostName }
        foreach ($addr in $hostEntry.AddressList) {
            if ($addr.IPAddressToString) { $localNames += $addr.IPAddressToString }
        }
    } catch {}
    $localNames = @($localNames | Where-Object { $_ } | ForEach-Object { $_.ToLowerInvariant() } | Select-Object -Unique)
    if ($name -in $localNames) { return $true }
    $shortLocalNames = @($localNames | ForEach-Object { $_.Split('.')[0] } | Select-Object -Unique)
    if ($shortName -in $shortLocalNames) { return $true }
    return $false
}

function Add-BrokerArgument {
    param([hashtable]$Arguments, [string]$ConnectionBroker)
    if ($ConnectionBroker -and -not (Test-LRIsLocalHost -ServerName $ConnectionBroker)) {
        $Arguments['ConnectionBroker'] = $ConnectionBroker
    }
}

function Resolve-LRCollection {
    param([string]$RequestedCollection, [string]$ConnectionBroker)

    $lookup = @{}
    Add-BrokerArgument -Arguments $lookup -ConnectionBroker $ConnectionBroker
    if ($RequestedCollection) {
        try {
            $collection = Get-RDSessionCollection -CollectionName $RequestedCollection @lookup -ErrorAction Stop
        } catch {
            if ($ConnectionBroker -and (Test-LRIsLocalHost -ServerName $ConnectionBroker)) {
                $collection = Get-RDSessionCollection -CollectionName $RequestedCollection -ErrorAction Stop
            } else {
                throw
            }
        }
        if (-not $collection) { throw "RDS collection '$RequestedCollection' was not found." }
        return $RequestedCollection
    }

    try {
        $collections = @(Get-RDSessionCollection @lookup -ErrorAction Stop)
    } catch {
        if ($ConnectionBroker -and (Test-LRIsLocalHost -ServerName $ConnectionBroker)) {
            $collections = @(Get-RDSessionCollection -ErrorAction Stop)
        } else {
            throw
        }
    }
    if ($collections.Count -eq 0) {
        throw 'No RDS session collection was found. Create a collection in Server Manager first.'
    }
    if ($collections.Count -eq 1) {
        return [string]$collections[0].CollectionName
    }
    $quickCollection = $collections | Where-Object { [string]$_.CollectionName -eq 'QuickSessionCollection' } | Select-Object -First 1
    if ($quickCollection) {
        return 'QuickSessionCollection'
    }

    $localNames = @($env:COMPUTERNAME)
    try {
        $localNames += [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName
    } catch {}
    $localNames = @($localNames | Where-Object { $_ } | ForEach-Object { $_.ToLowerInvariant() } | Select-Object -Unique)

    $matches = @()
    foreach ($candidate in $collections) {
        try {
            $hostLookup = @{ CollectionName = [string]$candidate.CollectionName }
            Add-BrokerArgument -Arguments $hostLookup -ConnectionBroker $ConnectionBroker
            try {
                $hosts = @(Get-RDSessionHost @hostLookup -ErrorAction Stop)
            } catch {
                if ($ConnectionBroker -and (Test-LRIsLocalHost -ServerName $ConnectionBroker)) {
                    $hosts = @(Get-RDSessionHost -CollectionName [string]$candidate.CollectionName -ErrorAction Stop)
                } else {
                    throw
                }
            }
            foreach ($hostEntry in $hosts) {
                $hostName = [string]$hostEntry.SessionHost
                if ($hostName -and $localNames -contains $hostName.ToLowerInvariant()) {
                    $matches += [string]$candidate.CollectionName
                    break
                }
                if ($hostName -and $localNames -contains $hostName.Split('.')[0].ToLowerInvariant()) {
                    $matches += [string]$candidate.CollectionName
                    break
                }
            }
        } catch {}
    }
    $matches = @($matches | Select-Object -Unique)
    if ($matches.Count -eq 1) { return $matches[0] }

    $available = ($collections | ForEach-Object { $_.CollectionName }) -join ', '
    throw "Multiple RDS collections were found ($available). Configure the collection name for this server."
}

function Resolve-LRExecutable {
    param(
        [string]$FilePath,
        [string]$Alias,
        [string]$DisplayName
    )

    $expanded = [Environment]::ExpandEnvironmentVariables([string]$FilePath).Trim().Trim('"')
    if ($expanded.StartsWith('||')) { $expanded = '' }
    if ($expanded -and (Test-Path -LiteralPath $expanded -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $expanded).Path
    }
    if ($expanded -and (Test-Path -LiteralPath $expanded -PathType Container)) {
        $explorerCmd = Get-Command 'explorer.exe' -ErrorAction SilentlyContinue
        if ($explorerCmd -and $explorerCmd.Source) {
            return (Resolve-Path -LiteralPath $explorerCmd.Source).Path
        }
        return 'C:\Windows\explorer.exe'
    }

    $rawNames = @($expanded, $Alias, $DisplayName) | Where-Object { $_ } | Select-Object -Unique
    $names = @()
    foreach ($rawName in $rawNames) {
        $leaf = Split-Path -Leaf $rawName
        if (-not $leaf) { $leaf = $rawName }
        $names += $leaf
        if ([System.IO.Path]::GetExtension($leaf) -eq '') { $names += "$leaf.exe" }
    }
    $names = @($names | Where-Object { $_ } | Select-Object -Unique)

    foreach ($name in $names) {
        foreach ($registryPath in @(
            "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\$name",
            "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\$name",
            "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\$name"
        )) {
            try {
                $registryItem = Get-Item -LiteralPath $registryPath -ErrorAction Stop
                $registeredPath = [string]$registryItem.GetValue('')
                if ($registeredPath -and (Test-Path -LiteralPath $registeredPath -PathType Leaf)) {
                    return (Resolve-Path -LiteralPath $registeredPath).Path
                }
            } catch {}
        }
    }

    $shell = New-Object -ComObject WScript.Shell
    $startMenuRoots = @(
        'C:\ProgramData\Microsoft\Windows\Start Menu\Programs',
        (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    function Normalize-LRName([string]$Value) {
        return (($Value -replace '\.lnk$','' -replace '\.exe$','' -replace '[^a-zA-Z0-9]+','').ToLowerInvariant())
    }
    $normalizedNames = @($names | ForEach-Object { Normalize-LRName $_ } | Where-Object { $_ } | Select-Object -Unique)
    foreach ($root in $startMenuRoots) {
        $shortcuts = Get-ChildItem -LiteralPath $root -Filter '*.lnk' -File -Depth 2 -ErrorAction SilentlyContinue
        foreach ($shortcutFile in $shortcuts) {
            $shortcutName = Normalize-LRName ([System.IO.Path]::GetFileNameWithoutExtension($shortcutFile.Name))
            if (-not ($normalizedNames | Where-Object { $shortcutName -eq $_ -or $shortcutName.Contains($_) -or $_.Contains($shortcutName) } | Select-Object -First 1)) {
                continue
            }
            try {
                $shortcut = $shell.CreateShortcut($shortcutFile.FullName)
                if ($shortcut.TargetPath -and (Test-Path -LiteralPath $shortcut.TargetPath -PathType Leaf)) {
                    return (Resolve-Path -LiteralPath $shortcut.TargetPath).Path
                }
            } catch {}
        }
    }

    foreach ($name in $names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $command.Source).Path
        }
    }

    if ($expanded) {
        throw "Application executable '$expanded' was not found on this RDS server. Enter its full .exe path."
    }
    throw "Application executable for '$DisplayName' was not found on this RDS server. Enter its full .exe path."
}

function Test-LRPrivateProfilePath {
    param([string]$FilePath)

    if (-not $FilePath) { return $false }
    try {
        $fullPath = [System.IO.Path]::GetFullPath($FilePath)
    } catch {
        return $false
    }
    $usersRoot = [System.IO.Path]::GetFullPath((Join-Path $env:SystemDrive 'Users')).TrimEnd('\') + '\'
    return $fullPath.StartsWith($usersRoot, [System.StringComparison]::OrdinalIgnoreCase)
}

function Stage-LRRemoteApp {
    param([string]$FilePath, [string]$Alias)

    $resolvedPath = (Resolve-Path -LiteralPath $FilePath -ErrorAction Stop).Path
    if (Test-Path -LiteralPath $resolvedPath -PathType Container) {
        try {
            & icacls.exe $resolvedPath /grant '*S-1-5-32-545:(OI)(CI)RX' /C /Q | Out-Null
        } catch {}
        return @{
            file_path = "$env:SystemRoot\explorer.exe"
            source_file_path = $resolvedPath
            managed_file_path = ''
            staged = $false
        }
    }

    if (Test-LRPrivateProfilePath -FilePath $resolvedPath) {
        $sourceDirectory = Split-Path -Parent $resolvedPath
        if ($sourceDirectory -and (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
            try {
                & icacls.exe $sourceDirectory /grant '*S-1-5-32-545:(OI)(CI)RX' /C /Q | Out-Null
            } catch {}
        }
    }

    return @{
        file_path = $resolvedPath
        source_file_path = $resolvedPath
        managed_file_path = ''
        staged = $false
    }
}

function Get-LRStandaloneRemoteApp {
    param([string]$Alias)

    $keyPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList\Applications\$Alias"
    if (-not (Test-Path -LiteralPath $keyPath)) { return $null }
    $item = Get-ItemProperty -LiteralPath $keyPath -ErrorAction Stop
    return [pscustomobject]@{
        Alias = $Alias
        DisplayName = [string]$item.Name
        FilePath = [string]$item.Path
        CommandLineSetting = [int]$item.CommandLineSetting
        RequiredCommandLine = [string]$item.RequiredCommandLine
    }
}

function Set-LRStandaloneRemoteApp {
    param(
        [string]$Alias,
        [string]$DisplayName,
        [string]$FilePath,
        [string]$SourceFilePath,
        [string]$Arguments
    )

    $rootPath = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList'
    $appsPath = Join-Path $rootPath 'Applications'
    New-Item -Path $appsPath -Force -ErrorAction Stop | Out-Null
    New-ItemProperty -LiteralPath $rootPath -Name 'fDisabledAllowList' -PropertyType DWord -Value 1 -Force | Out-Null

    $actualPath = $FilePath
    $cmdArgs = $Arguments
    if (Test-Path -LiteralPath $SourceFilePath -PathType Container) {
        $actualPath = "$env:SystemRoot\explorer.exe"
        $cmdArgs = "`"$SourceFilePath`""
    }

    $aliasesToRegister = @($Alias, $DisplayName, ($Alias -replace '[^a-zA-Z0-9_-]+', '')) | Where-Object { $_ } | Select-Object -Unique
    foreach ($a in $aliasesToRegister) {
        $keyPath = Join-Path $appsPath $a
        New-Item -Path $keyPath -Force -ErrorAction SilentlyContinue | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'Name' -PropertyType String -Value $DisplayName -Force | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'Path' -PropertyType String -Value $actualPath -Force | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'VPath' -PropertyType String -Value $(if ($SourceFilePath -ne $actualPath) { $SourceFilePath } else { '' }) -Force | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'IconPath' -PropertyType String -Value $actualPath -Force | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'IconIndex' -PropertyType DWord -Value 0 -Force | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'ShowInTSWA' -PropertyType DWord -Value 0 -Force | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'CommandLineSetting' -PropertyType DWord -Value $(if ($cmdArgs) { 2 } else { 0 }) -Force | Out-Null
        New-ItemProperty -LiteralPath $keyPath -Name 'RequiredCommandLine' -PropertyType String -Value $cmdArgs -Force | Out-Null
    }
    return Get-LRStandaloneRemoteApp -Alias $Alias
}

function Remove-LRStandaloneRemoteApp {
    param([string]$Alias)

    $keyPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList\Applications\$Alias"
    $existed = Test-Path -LiteralPath $keyPath
    if ($existed) {
        Remove-Item -LiteralPath $keyPath -Recurse -Force -ErrorAction Stop
    }
    return $existed
}

try {
    $payloadJson = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($PayloadBase64))
    $payload = $payloadJson | ConvertFrom-Json
    $action = ([string]$payload.action).Trim().ToLowerInvariant()
    $alias = ([string]$payload.alias).Trim()
    $displayName = ([string]$payload.display_name).Trim()
    $requestedCollection = ([string]$payload.collection_name).Trim()
    $connectionBroker = ([string]$payload.connection_broker).Trim()

    if ($action -notin @('publish', 'remove')) { throw "Unsupported RemoteApp action '$action'." }
    if (-not $alias) { throw 'RemoteApp alias is required.' }
    if ($connectionBroker -and (Test-LRIsLocalHost -ServerName $connectionBroker)) {
        $connectionBroker = ''
    }
    $collectionName = ''
    $lookup = @{}
    $existing = $null
    $standaloneMode = $false
    $rdsFallbackReason = ''
    if ($requestedCollection -or $connectionBroker) {
        try {
            if (-not (Get-Module -ListAvailable -Name RemoteDesktop)) {
                throw 'The Windows RemoteDesktop PowerShell module is not installed. Install the RDS management tools first.'
            }
            Import-Module RemoteDesktop -ErrorAction Stop
            $collectionName = Resolve-LRCollection -RequestedCollection $requestedCollection -ConnectionBroker $connectionBroker
            $lookup = @{ CollectionName = $collectionName; Alias = $alias }
            Add-BrokerArgument -Arguments $lookup -ConnectionBroker $connectionBroker
            $existing = Get-RDRemoteApp @lookup -ErrorAction SilentlyContinue
        } catch {
            $standaloneMode = $true
            $rdsFallbackReason = $_.Exception.Message
            $collectionName = ''
            $existing = Get-LRStandaloneRemoteApp -Alias $alias
        }
    } else {
        try {
            if (-not (Get-Module -ListAvailable -Name RemoteDesktop)) {
                throw 'The Windows RemoteDesktop PowerShell module is not installed.'
            }
            Import-Module RemoteDesktop -ErrorAction Stop
            $collectionName = Resolve-LRCollection -RequestedCollection '' -ConnectionBroker ''
            $lookup = @{ CollectionName = $collectionName; Alias = $alias }
            $existing = Get-RDRemoteApp @lookup -ErrorAction SilentlyContinue
        } catch {
            $standaloneMode = $true
            $rdsFallbackReason = $_.Exception.Message
            $collectionName = ''
            $existing = Get-LRStandaloneRemoteApp -Alias $alias
        }
    }

    if ($action -eq 'remove') {
        if ($standaloneMode) {
            $removed = Remove-LRStandaloneRemoteApp -Alias $alias
        } elseif ($existing) {
            $remove = @{ CollectionName = $collectionName; Alias = $alias }
            Add-BrokerArgument -Arguments $remove -ConnectionBroker $connectionBroker
            Remove-RDRemoteApp @remove -Force -Confirm:$false -ErrorAction Stop
        }
        Write-LRResult -Result @{
            success = $true
            status = 'unpublished'
            message = if ($existing -or $removed) { 'RemoteApp removed from this RDS server.' } else { 'RemoteApp was already absent from this RDS server.' }
            alias = $alias
            remote_app_program = "||$alias"
            collection_name = $collectionName
            connection_broker = if ($standaloneMode) { '' } else { $connectionBroker }
            publication_mode = if ($standaloneMode) { 'standalone_registry' } else { 'rds_collection' }
        }
    }

    if (-not $displayName) { throw 'RemoteApp display name is required.' }
    $rawFilePath = [string]$payload.file_path
    $arguments = ([string]$payload.arguments).Trim()
    if (-not $arguments -and $rawFilePath -and (Test-Path -LiteralPath $rawFilePath -PathType Container)) {
        $arguments = $rawFilePath
    }
    $resolvedFilePath = Resolve-LRExecutable -FilePath $rawFilePath -Alias $alias -DisplayName $displayName
    $staging = Stage-LRRemoteApp -FilePath $resolvedFilePath -Alias $alias
    $filePath = [string]$staging.file_path
    if ($existing -and -not [bool]$payload.allow_path_change) {
        $existingPath = [System.IO.Path]::GetFullPath([string]$existing.FilePath)
        $requestedPath = [System.IO.Path]::GetFullPath($filePath)
        if (-not $existingPath.Equals($requestedPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "RemoteApp alias '$alias' already exists for '$existingPath'. Choose a different alias."
        }
    }
    if (-not $standaloneMode) {
        try {
            $remoteApp = @{
                CollectionName = $collectionName
                Alias = $alias
                DisplayName = $displayName
                FilePath = $filePath
                ShowInWebAccess = $true
            }
            Add-BrokerArgument -Arguments $remoteApp -ConnectionBroker $connectionBroker
            if ($arguments) {
                $remoteApp['CommandLineSetting'] = 'Require'
                $remoteApp['RequiredCommandLine'] = $arguments
            } else {
                $remoteApp['CommandLineSetting'] = 'DoNotAllow'
            }

            if ($existing) {
                Set-RDRemoteApp @remoteApp -ErrorAction Stop | Out-Null
                $operation = 'updated'
            } else {
                New-RDRemoteApp @remoteApp -ErrorAction Stop | Out-Null
                $operation = 'published'
            }
            $verified = Get-RDRemoteApp @lookup -ErrorAction Stop
        } catch {
            $standaloneMode = $true
            $rdsFallbackReason = $_.Exception.Message
        }
    }

    if ($standaloneMode) {
        $verified = Set-LRStandaloneRemoteApp -Alias $alias -DisplayName $displayName -FilePath $filePath -SourceFilePath ([string]$staging.source_file_path) -Arguments $arguments
        $operation = if ($existing) { 'updated' } else { 'published' }
    }

    if (-not $verified) { throw "RemoteApp '$alias' could not be verified after publication." }
    Write-LRResult -Result @{
        success = $true
        status = 'published'
        message = if ($standaloneMode) { "RemoteApp $operation on this standalone RDS server." } else { "RemoteApp $operation in the RDS collection." }
        operation = $operation
        alias = [string]$verified.Alias
        remote_app_program = "||$([string]$verified.Alias)"
        file_path = [string]$verified.FilePath
        source_file_path = [string]$staging.source_file_path
        managed_file_path = [string]$staging.managed_file_path
        managed_directory = [string]$staging.managed_directory
        staged = [bool]$staging.staged
        display_name = [string]$verified.DisplayName
        collection_name = $collectionName
        connection_broker = if ($standaloneMode) { '' } else { $connectionBroker }
        publication_mode = if ($standaloneMode) { 'standalone_registry' } else { 'rds_collection' }
        rds_fallback_reason = $rdsFallbackReason
    }
} catch {
    Write-LRResult -Result @{
        success = $false
        status = 'failed'
        message = $_.Exception.Message
    } -ExitCode 1
}
'''


def _decode_result(stdout):
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def run_remote_app_action(payload, timeout=180):
    """Run an idempotent RDS RemoteApp publish/remove action on Windows."""
    if platform.system().lower() != "windows":
        return {
            "success": False,
            "status": "failed",
            "message": "RemoteApp publishing must run on a Windows RDS server.",
        }

    encoded_payload = base64.b64encode(
        json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".ps1", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(_REMOTE_APP_SCRIPT)
            script_path = handle.name

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
                encoded_payload,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "status": "failed",
            "message": "RemoteApp publishing timed out on the Windows RDS server.",
        }
    except OSError as error:
        return {"success": False, "status": "failed", "message": str(error)}
    finally:
        if script_path:
            try:
                Path(script_path).unlink(missing_ok=True)
            except OSError:
                pass

    result = _decode_result(completed.stdout)
    if result is not None:
        if completed.returncode != 0:
            result["success"] = False
            result.setdefault("status", "failed")
        return result

    message = (completed.stderr or completed.stdout or "PowerShell returned an invalid response.").strip()
    return {"success": False, "status": "failed", "message": message}
