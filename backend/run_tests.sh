#!/bin/bash
set -e

# Change directory to the backend directory where this script is located
cd "$(dirname "$0")"

echo "============================================="
echo "🧪 Research Intelligence Backend Test Runner"
echo "============================================="

# 1. Setup / Repair Virtual Environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment 'venv'..."
    python3 -m venv venv
else
    # Check if the python executable works (handles broken link/framework errors)
    if ! ./venv/bin/python -c "import sys" &> /dev/null; then
        echo "⚠️  Virtual environment 'venv' appears broken or outdated. Repairing..."
        python3 -m venv --clear venv
    fi
fi

# 2. Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# 3. Ensure dependencies are installed
echo "Installing/verifying requirements..."
pip install --upgrade pip &> /dev/null
pip install -r requirements.txt &> /dev/null

# 4. Run Django Tests
echo "Running test suite..."
python manage.py test

echo "============================================="
echo "✅ Tests completed successfully!"
echo "============================================="
