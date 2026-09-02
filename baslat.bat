@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "NO_BROWSER=0"

if /I "%~1"=="--no-browser" set "NO_BROWSER=1"

if not exist "%PYTHON%" (
  echo Backend virtual environment was not found.
  echo Run: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\python -m pip install -r requirements.txt
  goto :error
)

if not exist "%FRONTEND_DIR%\node_modules\next" (
  echo Frontend dependencies were not found.
  echo Run: cd frontend ^&^& npm install
  goto :error
)

call :is_port_listening 8000
if not errorlevel 1 (
  echo Backend is already running on http://127.0.0.1:8000
) else (
  start "NEXUS API" /D "%BACKEND_DIR%" cmd /k ""%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
  echo Backend is starting on http://127.0.0.1:8000
)

call :is_port_listening 3000
if not errorlevel 1 (
  echo Frontend is already running on http://127.0.0.1:3000
) else (
  start "NEXUS WEB" /D "%FRONTEND_DIR%" cmd /k "node.exe "%FRONTEND_DIR%\node_modules\next\dist\bin\next" dev -H 127.0.0.1 --port 3000"
  echo Frontend is starting on http://127.0.0.1:3000
)

echo.
echo Waiting for NEXUS services...
call :wait_for_url "http://127.0.0.1:8000/api/health" "Backend"
if errorlevel 1 goto :error

call :wait_for_url "http://127.0.0.1:3000" "Frontend"
if errorlevel 1 goto :error

echo NEXUS AI TRADER
echo Frontend: http://127.0.0.1:3000
echo API health: http://127.0.0.1:8000/api/health

if "%NO_BROWSER%"=="0" (
  echo Opening the application in your browser...
  start "" "http://127.0.0.1:3000"
)

exit /b 0

:error
echo.
echo Startup could not continue. Press any key to close this window.
pause >nul
exit /b 1

:is_port_listening
netstat -ano | findstr /R /C:":%~1 " | findstr /I /R /C:"LISTEN" /C:"D.NLEN" >nul
exit /b %errorlevel%

:wait_for_url
for /L %%I in (1,1,45) do (
  powershell.exe -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
  if not errorlevel 1 (
    echo %~2 is ready.
    exit /b 0
  )
  ping 127.0.0.1 -n 2 >nul
)

echo %~2 did not become ready: %~1
exit /b 1
