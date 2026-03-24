#!/bin/bash

# Production startup script for Next.js + Express architecture
# Next.js (port 5000, external) proxies API requests to Express (port 5001, internal)
# NOTE: This assumes build-prod.sh has already been run

set -e

echo "🚀 Starting Express backend on port 5001 (internal)..."
# Start Express and redirect output to both stdout and log file
PORT=5001 NODE_ENV=production node dist/index.js 2>&1 | tee /tmp/express.log &
BACKEND_PID=$!

# Wait for backend to be ready with better error detection
echo "⏳ Waiting for Express backend..."
for i in {1..20}; do
  # Check if process is still running
  if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "❌ Express backend process died. Last logs:"
    tail -50 /tmp/express.log
    exit 1
  fi
  
  # Check if health endpoint responds
  if curl -f http://localhost:5001/healthz > /dev/null 2>&1; then
    echo "✅ Express backend is ready on port 5001!"
    break
  fi
  
  # Timeout after 20 attempts (40 seconds)
  if [ $i -eq 20 ]; then
    echo "❌ Express backend failed to respond after 40s. Logs:"
    cat /tmp/express.log
    exit 1
  fi
  
  echo "Waiting for Express backend... ($i/20)"
  sleep 2
done

echo "🚀 Starting Next.js app on port 5000 (external)..."
# Start Next.js in foreground to keep the process alive
# Set environment variables before exec
cd web
export PORT=5000
export NODE_ENV=production
exec npm start
