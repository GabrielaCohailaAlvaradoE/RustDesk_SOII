@echo off
title Compilador del Agente de Telemetria Windows - UPT
echo ==============================================================
echo Compilando Agente de Telemetria RustDesk a ejecutable .EXE
echo ==============================================================

cd /d "%~dp0"

echo 1. Instalando PyInstaller...
pip install pyinstaller requests psutil Pillow

echo 2. Generando ejecutable portable...
pyinstaller --noconfirm --onedir --windowed --name "RustDeskTelemetryAgent" ^
    --add-data "config.ini;." ^
    agent.py

echo.
echo ==============================================================
echo Compilacion exitosa.
echo El ejecutable se encuentra en: dist\RustDeskTelemetryAgent\
echo ==============================================================
pause
