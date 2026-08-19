
$pw = ConvertTo-SecureString 'Lr@2027' -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential ('administrator', $pw)
Invoke-Command -ComputerName 191.44.87.48 -Credential $cred -ScriptBlock {
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*python*' -or $_.CommandLine -like '*agent*' } | Select-Object ProcessId, Name, ExecutablePath, CommandLine
}
