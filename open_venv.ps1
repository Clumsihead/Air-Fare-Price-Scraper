$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv"

wt.exe -d $ProjectDir powershell.exe -NoExit -Command "& {
    `$env:VIRTUAL_ENV = '$VenvDir'
    `$env:PATH = '$VenvDir\Scripts;' + `$env:PATH
    Set-Location '$ProjectDir'

    Write-Host ''
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host '   Airfare Scraper - Virtual Environment' -ForegroundColor Cyan
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host ''

    Write-Host 'Python:' -ForegroundColor Yellow
    python --version

    Write-Host ''
    Write-Host 'Python executable:' -ForegroundColor Yellow
    (Get-Command python).Source

    Write-Host ''
}"