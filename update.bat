@echo off
echo =======================================
echo Updating toyxyz_manager...
echo =======================================
echo.

echo Pulling latest changes from git...
git pull
echo.

echo Installing/updating Python dependencies...
pip install -r requirements.txt
echo.

echo =======================================
echo Update complete!
echo =======================================
pause
