#!/bin/bash
# Bundle Lambda code locally without Docker

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LAMBDA_DIR="$SCRIPT_DIR/../../lambda"
BUILD_DIR="$SCRIPT_DIR/lambda-bundle"

echo "Creating Lambda bundle..."

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Install dependencies for Lambda's architecture (Linux x86_64)
echo "Installing dependencies for Lambda (Linux x86_64)..."
pip3 install -r "$LAMBDA_DIR/requirements.txt" \
    --platform manylinux2014_x86_64 \
    --target "$BUILD_DIR" \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    --upgrade \
    --quiet

# Copy Lambda code
echo "Copying Lambda code..."
cp -r "$LAMBDA_DIR"/*.py "$BUILD_DIR/"
if [ -d "$LAMBDA_DIR/knowledge" ]; then
    cp -r "$LAMBDA_DIR/knowledge" "$BUILD_DIR/"
fi

# Clean up
echo "Cleaning up..."
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf "$BUILD_DIR"/*.dist-info 2>/dev/null || true

echo "✓ Bundle created at: $BUILD_DIR"
echo "Size: $(du -sh "$BUILD_DIR" | cut -f1)"
