@echo off
title DIALux IFC Bridge
cd /d "%~dp0"
if exist "dist\DialuxIFCBridge\DialuxIFCBridge.exe" (
    start "" "dist\DialuxIFCBridge\DialuxIFCBridge.exe"
) else (
    python main.py
)
