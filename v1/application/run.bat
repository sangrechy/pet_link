@echo off
title project_pet_link Camera & Control Server
cd /d "%~dp0"
echo ========================================================
echo Starting project_pet_link Camera & Control Server...
echo Web UI will be available at: http://localhost:8000
echo ========================================================
python launch.py
pause
