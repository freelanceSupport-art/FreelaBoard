$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

$paths = @(
  "build",
  "FreelaBoard.spec",
  "__pycache__",
  "src\freelaboard_app\__pycache__",
  "tests\__pycache__",
  "tools\__pycache__",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache"
)

foreach ($path in $paths) {
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}

Write-Host "Cleaned generated caches and PyInstaller work files."
