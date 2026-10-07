@echo off
title Study Guard v2
echo Starting Study Guard v2...
python "%~dp0app.py"
if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo  Study Guard crashed. Error above.
    echo ============================================
    pause
)
