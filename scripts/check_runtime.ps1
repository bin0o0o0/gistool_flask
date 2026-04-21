# 运行时检查脚本。
#
# 用 ArcGIS Pro Python 启动一个最小检查，确认：
# 1. propy.bat 能启动。
# 2. 项目 .venv\Lib\site-packages 能被加入 sys.path。
# 3. Flask 必须优先从项目 .venv 导入，而不是从用户目录或 ArcGIS Pro 环境导入。

param(
    # 可选：ArcGIS Pro 如果不是默认安装路径，可以手动传入：
    # .\scripts\check_runtime.ps1 -PropyPath "D:\ArcGIS\Pro\bin\Python\Scripts\propy.bat"
    [string]$PropyPath = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DefaultPropy = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat"
$Propy = $PropyPath
if ($Propy -eq "") {
    $Propy = $env:ARCGIS_PROPY
}
if ($Propy -eq "") {
    $Propy = $DefaultPropy
}
if (-not (Test-Path $Propy)) {
    throw "Cannot find propy.bat. Pass -PropyPath or set ARCGIS_PROPY."
}

$CheckCode = @"
import sys
from pathlib import Path

root = Path(r"$ProjectRoot")
project_site = root / ".venv" / "Lib" / "site-packages"

sys.path.insert(0, str(root / "backend"))
from app import _ensure_runtime_site_packages

_ensure_runtime_site_packages()

try:
    import flask
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Flask import failed. Please run scripts/setup.ps1 first."
    ) from exc

flask_file = Path(flask.__file__).resolve()
project_site_resolved = project_site.resolve()

try:
    flask_file.relative_to(project_site_resolved)
except ValueError as exc:
    raise SystemExit(
        "Flask is importable, but it was not loaded from project .venv.\n"
        f"Flask file: {flask_file}\n"
        f"Expected under: {project_site_resolved}\n"
        "Please run scripts/setup.ps1 and make sure Flask is installed into project .venv."
    ) from exc

print("Flask OK:", getattr(flask, "__version__", "unknown"))
print("Flask file:", flask_file)
print("Project venv site:", project_site_resolved)
print("GISTOOL_RUNTIME_CHECK_OK")
"@

$CheckDir = Join-Path $ProjectRoot "output\runtime_check"
$CheckFile = Join-Path $CheckDir "gistool_runtime_check.py"

# 多行 Python 代码直接传给 propy.bat 的 -c 参数时，在部分 Windows 环境里会被批处理转义影响。
# 写入项目 output 目录下的临时检查文件再执行更稳，也更接近用户真实启动脚本的方式。
New-Item -ItemType Directory -Path $CheckDir -Force | Out-Null
Set-Content -Path $CheckFile -Value $CheckCode -Encoding UTF8

try {
    $RuntimeOutput = & $Propy $CheckFile
    $ExitCode = $LASTEXITCODE
    $RuntimeOutput | ForEach-Object { Write-Host $_ }

    if ($ExitCode -ne 0) {
        throw "ArcGIS Pro Python runtime check failed with exit code $ExitCode"
    }

    if (($RuntimeOutput -join "`n") -notmatch "GISTOOL_RUNTIME_CHECK_OK") {
        throw "ArcGIS Pro Python did not finish the project .venv Flask check."
    }
}
finally {
    Remove-Item -Path $CheckFile -ErrorAction SilentlyContinue
}
