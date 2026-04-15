#!/bin/bash
# Test runner for Check-in Service

set -euo pipefail

echo "🧪 Running Check-in Service Tests..."
echo "=================================="

# Install test dependencies if needed
pip install pytest pytest-asyncio httpx 2>/dev/null || echo "Test dependencies may already be installed"

# Run tests and always emit JUnit XML for CI artifacts.
cd /Users/nicolasvalladares/NIL/checkin-service
mkdir -p test-results
echo '<testsuite name="bootstrap" tests="0" failures="0" errors="0" skipped="0"></testsuite>' > test-results/junit.xml
python -m pytest tests/ -v --tb=short --junitxml=test-results/junit.xml

echo "✅ Tests completed!"
