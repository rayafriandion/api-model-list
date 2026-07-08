@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
python api_model_list.py shell %*
pause
