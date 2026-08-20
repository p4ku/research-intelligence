#!/bin/bash
# Do not use set -e so we can handle fallback logic manually

# Change directory to project root
cd "$(dirname "$0")/.."

echo "============================================="
echo "📊 Research Intelligence Diagram Builder"
echo "============================================="

# 1. Check and activate Virtual Environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip and install diagrams package
echo "Installing python dependencies..."
pip install --upgrade pip &> /dev/null
pip install diagrams &> /dev/null

# 2. Check for Graphviz (dot)
HAS_GRAPHVIZ=true
if ! command -v dot &> /dev/null; then
    echo "⚠️  Graphviz ('dot') not found."
    echo "Attempting to install graphviz via Homebrew..."
    if command -v brew &> /dev/null; then
        if brew install graphviz; then
            echo "✅ Graphviz installed successfully."
        else
            echo "❌ Homebrew install failed. (Likely permissions or Cellar is owned by another user)."
            HAS_GRAPHVIZ=false
        fi
    else
        echo "❌ Homebrew is not available."
        HAS_GRAPHVIZ=false
    fi
fi

# 3. Generate Diagrams
if [ "$HAS_GRAPHVIZ" = true ]; then
    echo "Generating diagrams via Python-Diagrams (Graphviz)..."
    if python3 docs/diagrams/architecture.py && python3 docs/diagrams/pipeline_stages.py && python3 docs/diagrams/llm_providers.py && python3 docs/diagrams/ocr_providers.py; then
        echo "✅ Python-Diagrams rendered successfully!"
        exit 0
    else
        echo "⚠️  Python-Diagrams rendering failed. Falling back to Mermaid rendering..."
    fi
else
    echo "💡 Falling back to Mermaid rendering..."
fi

# 4. Fallback to Mermaid rendering (no Graphviz required, needs internet access)
echo "Generating diagrams via Mermaid (Mermaid.ink / mermaid-cli)..."
python3 docs/diagrams/build_mermaid.py
python3 docs/generate_db_schema.py

echo "============================================="
echo "🎉 Diagrams generated successfully in docs/images/"
ls -la docs/images/
echo "============================================="
