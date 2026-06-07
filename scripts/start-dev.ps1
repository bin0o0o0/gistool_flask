param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$PropyPath = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat",
    [string]$GisPythonPath = "D:\python3.9.5\python.exe",
    [switch]$SkipFrontend,
    [switch]$KeepExisting
)

$ErrorActionPreference = "Stop"

function Stop-PortProcess {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        if ($processId -and $processId -ne $PID) {
            Write-Host "Stopping existing process on port $Port (PID $processId)"
            Stop-Process -Id $processId -Force
        }
    }
}

function Start-Backend {
    param(
        [string]$Name,
        [string]$ServiceMode,
        [string]$Executable
    )

    if (-not (Test-Path $Executable)) {
        throw "$Name runtime not found: $Executable"
    }

    $command = "`$env:GIS_TOOL_SERVICE='$ServiceMode'; & '$Executable' backend\run.py"
    Write-Host "Starting $Name ($ServiceMode)"
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $command) `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Minimized
}

function Start-Frontend {
    Write-Host "Starting frontend on port 5173"
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "cd frontend; npm run dev -- --host 0.0.0.0 --port 5173") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Minimized
}

if (-not $KeepExisting) {
    foreach ($port in @(5000, 5001, 5002, 5173)) {
        Stop-PortProcess -Port $port
    }
}

Start-Backend -Name "map-output backend" -ServiceMode "render" -Executable $PropyPath
Start-Backend -Name "watershed extraction backend" -ServiceMode "watershed" -Executable $GisPythonPath
Start-Backend -Name "watershed boundary backend" -ServiceMode "watershed-boundary" -Executable $GisPythonPath

if (-not $SkipFrontend) {
    Start-Frontend
}

Write-Host ""
Write-Host "Fixed ports:"
Write-Host "  5000 -> map-output / ArcGIS Pro Python"
Write-Host "  5001 -> watershed-extract / normal GIS Python"
Write-Host "  5002 -> watershed-boundary-generator / normal GIS Python"
Write-Host "  5173 -> Vite frontend"
