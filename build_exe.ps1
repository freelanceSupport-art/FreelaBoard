$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

@'
import importlib.util
import subprocess
import sys

required = {
    "PyInstaller": "pyinstaller",
    "PIL": "pillow",
}

for module_name, package_name in required.items():
    if importlib.util.find_spec(module_name) is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
'@ | python -

python tools\make_icon.py

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name FreelaBoard `
  --paths src `
  --icon assets\generated\freelaboard.ico `
  --add-data "assets\generated\freelaboard.ico;assets\generated" `
  --add-data "assets\generated\freelaboard.png;assets\generated" `
  main.py

Write-Host ""
Write-Host "Built: $ProjectRoot\dist\FreelaBoard.exe"
