@echo off
setlocal
set "FP_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%FP_PYTHON%" (
  "%FP_PYTHON%" -B "%~dp0app.py" gui
) else (
  py -3 -B "%~dp0app.py" gui
)
if errorlevel 1 (
  echo Please install dependencies from fp_competition\requirements.txt in your Python environment.
  pause
)
endlocal
