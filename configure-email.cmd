@echo off
"%~dp0.venv\Scripts\python.exe" -B "%~dp0configure_email.py"
if errorlevel 1 pause
