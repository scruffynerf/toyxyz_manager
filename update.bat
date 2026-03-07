@echo off
setlocal

cd /d "%~dp0"

echo =======================================
echo Updating toyxyz_manager...
echo =======================================
echo.

echo Pulling latest changes from git...
git pull
echo.

echo Checking for venv...
if not exist venv (
    echo [ERROR] venv not found! Please run setup_env.bat first to create the environment.
    pause
    exit /b 1
)

echo Activating venv...
call venv\Scripts\activate

echo Installing/updating Python dependencies...
python -m pip install -r requirements.txt
echo.

echo =======================================
echo Update complete!
echo =======================================
pause
