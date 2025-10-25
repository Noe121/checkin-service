#!/bin/bash
# Test runner for Check-in Service

echo "🧪 Running Check-in Service Tests..."
echo "=================================="

# Install test dependencies if needed
pip install pytest pytest-asyncio httpx 2>/dev/null || echo "Test dependencies may already be installed"

# Run the tests
cd /Users/nicolasvalladares/NIL/checkin-service
python -m pytest tests/ -v --tb=short

echo "✅ Tests completed!"