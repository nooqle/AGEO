#!/bin/bash
# Specta AI - Development Environment Startup Script
# Usage: ./scripts/dev.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Specta AI Development Environment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if .env.local exists
if [ ! -f "backend/.env.local" ]; then
    echo -e "${YELLOW}Warning: backend/.env.local not found${NC}"
    echo -e "${YELLOW}Copying from backend/.env.local.example...${NC}"
    cp backend/.env.local.example backend/.env.local
    echo -e "${YELLOW}Please edit backend/.env.local and add your API keys${NC}"
    echo ""
fi

if [ ! -f "frontend/.env.local" ]; then
    echo -e "${YELLOW}Warning: frontend/.env.local not found${NC}"
    echo -e "${YELLOW}Copying from frontend/.env.local.example...${NC}"
    cp frontend/.env.local.example frontend/.env.local
    echo ""
fi

# Check backend virtual environment
if [ ! -d "backend/venv" ] && [ ! -d "backend/.venv" ]; then
    echo -e "${YELLOW}Creating backend virtual environment...${NC}"
    cd backend
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to create virtual environment${NC}"
        exit 1
    fi
    cd ..
fi

# Activate virtual environment
if [ -d "backend/venv" ]; then
    source backend/venv/bin/activate
elif [ -d "backend/.venv" ]; then
    source backend/.venv/bin/activate
fi

# Install backend dependencies if needed
if [ ! -f "backend/venv/.dependencies_installed" ]; then
    echo -e "${YELLOW}Installing backend dependencies...${NC}"
    cd backend
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        touch venv/.dependencies_installed
    fi
    cd ..
fi

# Check frontend dependencies
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    cd frontend
    npm install
    cd ..
fi

echo ""
echo -e "${GREEN}Starting services...${NC}"
echo ""

# Start backend
echo -e "${BLUE}Starting backend (port 8000)...${NC}"
cd backend
source venv/bin/activate
uvicorn app.main:socket_app --reload --port 8000 &
BACKEND_PID=$!
cd ..

# Wait for backend to start
sleep 3

# Check if backend started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}Failed to start backend${NC}"
    exit 1
fi

# Start frontend
echo -e "${BLUE}Starting frontend (port 3000)...${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Development Environment Started!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${BLUE}Frontend:${NC} http://localhost:3000"
echo -e "  ${BLUE}Backend:${NC}  http://localhost:8000"
echo -e "  ${BLUE}API Docs:${NC} http://localhost:8000/docs"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Function to cleanup processes
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping services...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait
    echo -e "${GREEN}All services stopped${NC}"
    exit 0
}

# Set up signal handlers
trap cleanup INT TERM

# Wait for processes
wait
