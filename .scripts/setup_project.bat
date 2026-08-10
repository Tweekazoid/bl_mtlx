@echo off
setlocal EnableDelayedExpansion

for %%I in ("%~dp0..") do set "REPO_FOLDER=%%~fI"
set "THIS_FOLDER=%~dp0"

echo Script directory: !THIS_FOLDER!
echo Repository directory: !REPO_FOLDER!

where uv >nul 2>nul
if errorlevel 1 (
    echo "'uv' command not found in PATH. Attempting to install 'uv'..."
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression"

    if errorlevel 1 (
        echo "Failed to install 'uv'. Please install it manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit /b 1
    )

    set Path=C:\Users\%USERNAME%\.local\bin;!Path!

    where uv >nul 2>nul
    if errorlevel 1 (
        echo "'uv' command still not found in PATH after installation."
        exit /b 1
    )
)

uv self update

pushd "!REPO_FOLDER!"

echo ----------------------------------------
echo Setting up project at: !REPO_FOLDER!
echo ----------------------------------------

if not exist ".venv" (
    echo Creating virtual environment...
    uv venv .venv
) else (
    echo Reusing existing virtual environment.
)

if exist "pyproject.toml" (
    echo Syncing dependencies from pyproject.toml...
    uv sync --all-groups
) else (
    echo No pyproject.toml found at !REPO_FOLDER!, skipping dependency sync.
)

echo Virtual environment setup completed successfully.
echo ----------------------------------------
popd >nul
endlocal
