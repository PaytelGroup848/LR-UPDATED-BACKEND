
Write-Host '=== 1. TSAPPALLOWLIST REGISTRY ENTRIES ==='
 = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList\Applications'
if (Test-Path ) {
    Get-ChildItem  | ForEach-Object {
         = Get-ItemProperty .PSPath
        Write-Host ('Alias: ' + .PSChildName + ' | Path: ' + .Path + ' | CmdLineSetting: ' + .CommandLineSetting)
    }
} else {
    Write-Host 'TSAppAllowList Key Missing'
}

Write-Host ''
Write-Host '=== 2. ACL & INHERITANCE STATUS ==='
foreach ( in @('C:\PublicFolders', 'C:\TallyPrime')) {
    if (Test-Path ) {
         = Get-Acl 
        Write-Host ('Dir: ' +  + ' | Owner: ' + .Owner + ' | InheritanceDisabled: ' + .AreAccessRulesProtected)
        Write-Host ('   ACL Rules: ' + (.AccessToString -replace '
', ' ; '))
    } else {
        Write-Host ('Dir Missing: ' + )
    }
}
