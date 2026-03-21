@echo off
REM ─── JobCraft One-Command Startup Script (Windows) ───
REM Usage: Double-click this file or run: run.bat

echo 🚀 Starting JobCraft...
echo.

cd /d "%~dp0"

REM 1. Python virtual environment
if not exist ".venv" (
    echo 📦 Creating Python virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

REM 2. Install Python dependencies
echo 📦 Installing Python dependencies...
pip install -r backend\requirements.txt --quiet

REM 3. Install Playwright browsers
echo 🌐 Installing Playwright browsers if needed...
playwright install chromium 2>nul

REM 4. Node dependencies
if not exist "frontend\node_modules" (
    echo 📦 Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
)

REM 5. Create .env from template if missing
if not exist ".env" (
    echo ⚙️  Creating .env from template — please add your API key!
    copy .env.example .env
)

REM 6. Create data directories
if not exist "data\resumes\base" mkdir "data\resumes\base"
if not exist "data\resumes\tailored" mkdir "data\resumes\tailored"
if not exist "data\jobs" mkdir "data\jobs"

REM 7. Start backend
echo.
echo 🔧 Starting backend on http://localhost:8000...
start "JobCraft Backend" cmd /c "cd backend && ..\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8080 --reload"

REM 8. Start frontend
echo 🎨 Starting frontend on http://localhost:5173...
start "JobCraft Frontend" cmd /c "cd frontend && npm run dev"

REM 9. Wait for servers
timeout /t 4 /nobreak >nul

REM 10. Open browser
start http://localhost:5173

echo.
echo ✅ JobCraft is running!
echo    Frontend: http://localhost:5173
echo    Backend:  http://localhost:8080
echo    API Docs: http://localhost:8080/docs
echo.
echo    Default login: admin / jobcraft2024
echo.
echo Close this window to stop. (Close the backend/frontend windows too)
pause
