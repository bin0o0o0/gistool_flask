# 项目依赖安装脚本。
#
# 这个脚本只负责把 Flask 等普通 Python 包安装到项目自己的 `.venv`。
# ArcPy 不会安装到 `.venv`，仍然由 ArcGIS Pro 的 `propy.bat` 提供。

param(
    [string]$IndexUrl = "",
    [string]$PythonPath = "python3.9"
)

# 参数说明：
# -IndexUrl：可选，网络不稳定时可传国内镜像，例如：
#   .\scripts\setup.ps1 -IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple
# -PythonPath：固定要求用 Python 3.9 创建项目 .venv；Windows 上可以传 py 启动器或 python.exe 完整路径。

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $ProjectRoot "backend\requirements.txt"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Assert-Python39 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable
    )

    $Version = & $Executable -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to run Python executable: $Executable"
    }
    if (($Version | Select-Object -First 1).Trim() -ne "3.9") {
        throw "This project requires Python 3.9 for .venv. Current $Executable version is $Version."
    }
}

Write-Host "Checking Python version for project .venv..."
Assert-Python39 -Executable $PythonPath

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating project virtual environment: $VenvDir"
    Invoke-Checked { & $PythonPath -m venv $VenvDir }
}
else {
    Write-Host "Checking existing project .venv Python version..."
    Assert-Python39 -Executable $VenvPython
}

Write-Host "Installing backend dependencies into project .venv..."
$PipArgs = @("-m", "pip", "install", "--disable-pip-version-check", "-r", $Requirements)
if ($IndexUrl -ne "") {
    $PipArgs = @("-m", "pip", "install", "--disable-pip-version-check", "-i", $IndexUrl, "-r", $Requirements)
}

try {
    Invoke-Checked { & $VenvPython @PipArgs }
}
catch {
    Write-Host ""
    Write-Host "Dependency installation failed."
    Write-Host "Please check network/proxy settings, then run this script again."
    Write-Host "If PyPI is slow, try:"
    Write-Host "  .\scripts\setup.ps1 -IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple"
    throw
}

Write-Host "Verifying Flask inside project .venv..."
Invoke-Checked { & $VenvPython -c "import flask; print('Flask installed:', getattr(flask, '__version__', 'unknown')); print('Flask file:', flask.__file__)" }

Write-Host ""
Write-Host "Setup complete."
Write-Host "Flask is now installed under: $VenvDir"
Write-Host "Start the backend with ArcGIS Pro Python:"
Write-Host '  & "<your ArcGIS Pro>\bin\Python\Scripts\propy.bat" backend\run.py'
