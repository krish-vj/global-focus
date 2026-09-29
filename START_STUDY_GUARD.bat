@echo off
title Study Guard
echo Starting Study Guard...
python "%~dp0study_guard.py"
if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo  Study Guard crashed. Error above.
    echo ============================================
    pause
)
