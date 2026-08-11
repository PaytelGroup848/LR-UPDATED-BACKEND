@echo off
setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Please right-click this file and choose "Run as administrator".
  pause
  exit /b 1
)

netsh advfirewall firewall delete rule name="LR Platform API Gateway 8000" >nul 2>&1
netsh advfirewall firewall delete rule name="LR Platform Frontend 3000" >nul 2>&1
netsh advfirewall firewall delete rule name="LR Platform Guacamole 8080" >nul 2>&1

netsh advfirewall firewall add rule name="LR Platform API Gateway 8000" dir=in action=allow protocol=TCP localport=8000 profile=any
netsh advfirewall firewall add rule name="LR Platform Frontend 3000" dir=in action=allow protocol=TCP localport=3000 profile=any
netsh advfirewall firewall add rule name="LR Platform Guacamole 8080" dir=in action=allow protocol=TCP localport=8080 profile=any

echo.
echo LR Platform ports are open:
echo   8000 API / Admin Panel backend
echo   3000 Web frontend
echo   8080 Guacamole
echo.
pause
