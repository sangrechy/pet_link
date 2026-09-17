@echo off
title PetVision Camera & Control Server
cd /d "%~dp0"
echo ========================================================
echo Starting PetVision Camera & Control Server...
echo Web UI will be available at: http://localhost:8000
echo ========================================================
python launch.py
pause
