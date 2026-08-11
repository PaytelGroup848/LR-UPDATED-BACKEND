$ErrorActionPreference = "Stop"

$rules = @(
    @{ Name = "LR Platform Frontend 3000"; Port = 3000 },
    @{ Name = "LR Platform API Gateway 8000"; Port = 8000 },
    @{ Name = "LR Platform Guacamole 8080"; Port = 8080 }
)

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -DisplayName $rule.Name -Enabled True -Direction Inbound -Action Allow
        Set-NetFirewallPortFilter -AssociatedNetFirewallRule $existing -Protocol TCP -LocalPort $rule.Port
    }
    else {
        New-NetFirewallRule `
            -DisplayName $rule.Name `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $rule.Port `
            -Action Allow | Out-Null
    }
}

Write-Host "LR Platform firewall ports are open: 3000, 8000, 8080"
