#!/bin/bash
# ─── JobCraft One-Command Startup Script ───
# Usage: bash run.sh

set -e

echo "🚀 Starting JobCraft..."
echo ""

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Python virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r backend/requirements.txt --quiet

# 3. Install Playwright browsers (first run only)
if ! python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    echo "🌐 Installing Playwright browsers (one-time setup)..."
    playwright install chromium
fi

# 4. Node dependencies
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd frontend && npm install && cd ..
fi

# 5. Create .env from template if missing
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env from template — please add your API key!"
    cp .env.example .env
fi

# 6. Create data directories
mkdir -p data/resumes/base data/resumes/tailored data/jobs

# 7. Start backend (FastAPI on port 8000)
echo ""
echo "🔧 Starting backend on http://localhost:8080..."
cd backend
uvicorn main:app --host 127.0.0.1 --port 8080 --reload &
BACKEND_PID=$!
cd ..

# 8. Start frontend (Vite on port 5173)
echo "🎨 Starting frontend on http://localhost:5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# 9. Wait for servers to start
sleep 3

# 10. Open browser
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5173
elif command -v open &> /dev/null; then
    open http://localhost:5173
fi

echo ""
echo "✅ JobCraft is running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8080"
echo "   API Docs: http://localhost:8080/docs"
echo ""
echo "   Default login: admin / jobcraft2024"
echo ""
echo "Press Ctrl+C to stop."

# Trap Ctrl+C to kill both processes
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; echo 'JobCraft stopped.'; exit 0" SIGINT SIGTERM

wait
