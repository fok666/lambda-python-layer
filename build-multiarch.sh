#!/bin/bash
set -e

# Default values
PYTHON_VERSION="3.14"
IMAGE_NAME="lambda-zipper"
REQUIREMENTS_FILE="requirements.txt"
SINGLE_PACKAGE=""
BUILD_AMD64=true
BUILD_ARM64=true
SINGLE_FILE=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --python)
            PYTHON_VERSION="$2"
            shift 2
            ;;
        -r|--requirements)
            REQUIREMENTS_FILE="$2"
            shift 2
            ;;
        --package)
            SINGLE_PACKAGE="$2"
            REQUIREMENTS_FILE=""
            shift 2
            ;;
        --image)
            IMAGE_NAME="$2"
            shift 2
            ;;
        --skip-x86|--skip-amd64)
            BUILD_AMD64=false
            shift
            ;;
        --skip-arm64)
            BUILD_ARM64=false
            shift
            ;;
        --individual)
            SINGLE_FILE=false
            shift
            ;;
        --help)
            echo "Usage: ./build-multiarch.sh [OPTIONS]"
            echo ""
            echo "Default behavior:"
            echo "  - Uses Python 3.14 (latest)"
            echo "  - Reads from requirements.txt"
            echo "  - Builds both x86_64 and arm64 architectures"
            echo "  - Creates single combined archive per architecture"
            echo ""
            echo "Options:"
            echo "  --python VERSION        Python version to use (default: 3.14)"
            echo "                         Supported: 3.10, 3.11, 3.12, 3.13, 3.14"
            echo "  -r, --requirements FILE Path to requirements.txt (default: requirements.txt)"
            echo "  --package NAME          Single package name (disables requirements.txt mode)"
            echo "  --image NAME           Docker image name (default: lambda-zipper)"
            echo "  --skip-x86, --skip-amd64  Skip x86_64 build"
            echo "  --skip-arm64           Skip arm64 build"
            echo "  --individual           Create individual archives per package (not combined)"
            echo "  --help                 Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./build-multiarch.sh                    # Build with all defaults"
            echo "  ./build-multiarch.sh --python 3.13      # Use Python 3.13"
            echo "  ./build-multiarch.sh --skip-arm64       # Build only x86_64"
            echo "  ./build-multiarch.sh --individual       # Create separate archives per package"
            echo "  ./build-multiarch.sh --package numpy    # Build single package"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate Python version
if [[ ! "$PYTHON_VERSION" =~ ^3\.(10|11|12|13|14)$ ]]; then
    echo "Error: Unsupported Python version: $PYTHON_VERSION"
    echo "Supported versions: 3.10, 3.11, 3.12, 3.13, 3.14"
    exit 1
fi

# Validate architecture selection
if [ "$BUILD_AMD64" = false ] && [ "$BUILD_ARM64" = false ]; then
    echo "Error: Cannot skip both architectures. At least one must be built."
    exit 1
fi

# Check if requirements file or package is specified
if [ -z "$SINGLE_PACKAGE" ]; then
    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        echo "Error: Requirements file not found: $REQUIREMENTS_FILE"
        echo "Use --package for single package mode or provide a valid requirements.txt file"
        exit 1
    fi
fi


echo "==================================="
echo "Lambda Package Builder"
echo "==================================="
echo "Python version: ${PYTHON_VERSION}"
if [ -n "$REQUIREMENTS_FILE" ]; then
    echo "Requirements: ${REQUIREMENTS_FILE}"
    echo "Output mode: $([ "$SINGLE_FILE" = true ] && echo "Single combined archive per arch" || echo "Individual archives per package")"
else
    echo "Package: ${SINGLE_PACKAGE}"
fi
echo "Architectures: $([ "$BUILD_AMD64" = true ] && echo -n "x86_64 " || echo -n "")$([ "$BUILD_ARM64" = true ] && echo -n "arm64" || echo -n "")"
echo "==================================="
echo ""

# Create output directory
mkdir -p output

# Build and run for x86_64 (amd64)
if [ "$BUILD_AMD64" = true ]; then
    echo "Building for x86_64 (amd64)..."
    docker buildx build \
        --platform linux/amd64 \
        --build-arg PYTHON_VERSION=${PYTHON_VERSION} \
        -t ${IMAGE_NAME}:amd64-py${PYTHON_VERSION} \
        --load \
        .

    if [ -n "$REQUIREMENTS_FILE" ]; then
        if [ "$SINGLE_FILE" = true ]; then
            docker run --rm \
                -e SINGLE_FILE=true \
                -v "$(pwd)/${REQUIREMENTS_FILE}:/input/requirements.txt" \
                -v "$(pwd)/output:/package" \
                ${IMAGE_NAME}:amd64-py${PYTHON_VERSION}
        else
            docker run --rm \
                -v "$(pwd)/${REQUIREMENTS_FILE}:/input/requirements.txt" \
                -v "$(pwd)/output:/package" \
                ${IMAGE_NAME}:amd64-py${PYTHON_VERSION}
        fi
    else
        docker run --rm \
            -v "$(pwd)/output:/package" \
            ${IMAGE_NAME}:amd64-py${PYTHON_VERSION} \
            ${SINGLE_PACKAGE}
    fi
    echo ""
fi

# Build and run for arm64 (aarch64)
if [ "$BUILD_ARM64" = true ]; then
    echo "Building for arm64 (aarch64)..."
    docker buildx build \
        --platform linux/arm64 \
        --build-arg PYTHON_VERSION=${PYTHON_VERSION} \
        -t ${IMAGE_NAME}:arm64-py${PYTHON_VERSION} \
        --load \
        .

    if [ -n "$REQUIREMENTS_FILE" ]; then
        if [ "$SINGLE_FILE" = true ]; then
            docker run --rm \
                -e SINGLE_FILE=true \
                -v "$(pwd)/${REQUIREMENTS_FILE}:/input/requirements.txt" \
                -v "$(pwd)/output:/package" \
                ${IMAGE_NAME}:arm64-py${PYTHON_VERSION}
        else
            docker run --rm \
                -v "$(pwd)/${REQUIREMENTS_FILE}:/input/requirements.txt" \
                -v "$(pwd)/output:/package" \
                ${IMAGE_NAME}:arm64-py${PYTHON_VERSION}
        fi
    else
        docker run --rm \
            -v "$(pwd)/output:/package" \
            ${IMAGE_NAME}:arm64-py${PYTHON_VERSION} \
            ${SINGLE_PACKAGE}
    fi
    echo ""
fi

echo ""
echo "==================================="
echo "Build completed successfully!"
echo "Output files in: ./output/"
ls -lh output/
echo "==================================="
