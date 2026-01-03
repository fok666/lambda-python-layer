#!/bin/bash
set -e

ARCH=$(uname -m)
PYTHON_VERSION=$(python3 --version | awk '{print $2}' | cut -d. -f1,2)

echo "Building packages for Python ${PYTHON_VERSION} on ${ARCH}"

# Check if requirements.txt is provided
if [ -f "/input/requirements.txt" ]; then
    
    # Check if SINGLE_FILE mode is enabled
    if [ "${SINGLE_FILE}" = "true" ]; then
        echo "Processing requirements.txt - creating single combined archive"
        
        # Create temp directory for all packages
        mkdir -p /temp
        
        # Install all packages at once
        echo "Installing all packages from requirements.txt..."
        python3 -m pip install -r /input/requirements.txt -t /temp --no-cache-dir
        
        # Create combined archive with Lambda Layer structure
        OUTPUT_FILE="/package/combined-python${PYTHON_VERSION}-${ARCH}.zip"
        cd /temp
        
        # Create python/lib/pythonX.Y/site-packages structure for Lambda layers
        mkdir -p python/lib/python${PYTHON_VERSION}/site-packages
        mv * python/lib/python${PYTHON_VERSION}/site-packages/ 2>/dev/null || true
        
        zip -r -q "${OUTPUT_FILE}" python/
        echo "✓ Created: ${OUTPUT_FILE}"
        
        # Cleanup
        cd /
        rm -rf /temp
        
        echo ""
        echo "========================================="
        echo "Combined package built successfully!"
        echo "========================================="
    else
        echo "Processing requirements.txt - creating individual archives for each package"
        
        # Read each line from requirements.txt
        while IFS= read -r line || [ -n "$line" ]; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        
        # Extract package name (remove version specifiers)
        PACKAGE=$(echo "$line" | sed 's/[<>=!].*//' | tr -d ' ')
        
        echo ""
        echo "========================================="
        echo "Building package: ${PACKAGE}"
        echo "========================================="
        
        # Create temp directory for this package
        mkdir -p /temp
        
        # Install the package
        python3 -m pip install "$line" -t /temp --no-cache-dir
        
        # Create archive with Lambda Layer structure
        OUTPUT_FILE="/package/${PACKAGE}-python${PYTHON_VERSION}-${ARCH}.zip"
        cd /temp
        
        # Create python/lib/pythonX.Y/site-packages structure for Lambda layers
        mkdir -p python/lib/python${PYTHON_VERSION}/site-packages
        mv * python/lib/python${PYTHON_VERSION}/site-packages/ 2>/dev/null || true
        
        zip -r -q "${OUTPUT_FILE}" python/
        echo "✓ Created: ${OUTPUT_FILE}"
        
        # Cleanup for next package
        cd /
        rm -rf /temp
        
    done < /input/requirements.txt
    
    echo ""
    echo "========================================="
    echo "All packages built successfully!"
    echo "========================================="
    fi
else
    # Single package mode (backward compatibility)
    if [ -z "$1" ]; then
        echo "Usage: docker run --rm -v \$(pwd):/package lambdazipper PACKAGE_NAME"
        echo "   or: docker run --rm -v \$(pwd)/requirements.txt:/input/requirements.txt -v \$(pwd):/package lambdazipper"
        exit 1
    fi
    
    PACKAGE=$1
    echo "Building single package: ${PACKAGE}"
    
    mkdir -p /temp
    python3 -m pip install ${PACKAGE} -t /temp --no-cache-dir
    
    OUTPUT_FILE="/package/${PACKAGE}-python${PYTHON_VERSION}-${ARCH}.zip"
    cd /temp
    
    # Create python/lib/pythonX.Y/site-packages structure
    mkdir -p python/lib/python${PYTHON_VERSION}/site-packages
    mv * python/lib/python${PYTHON_VERSION}/site-packages/ 2>/dev/null || true
    
    zip -r -q "${OUTPUT_FILE}" python/
    echo "✓ Created: ${OUTPUT_FILE}"
    
    # Cleanup
    rm -rf /temp
fi