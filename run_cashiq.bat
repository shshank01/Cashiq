@echo off
echo ============================================================
echo           Starting CashIQ Financial Platform
echo ============================================================
echo.
echo Launching Backend on http://localhost:8000 ...
start "CashIQ Backend (FastAPI)" cmd /k "cd backend && python run.py"

timeout /t 3 /nobreak >nul

echo Launching Frontend on http://localhost:3000 ...
start "CashIQ Frontend (Vite)" cmd /k "cd frontend && npm run dev"

echo.
echo ============================================================
echo CashIQ is starting!
echo Frontend: http://localhost:3000
echo Backend API docs: http://localhost:8000/docs
echo Demo Credentials: demo@cashiq.io / password123
echo ============================================================
pause
