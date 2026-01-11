# Python Package Builder for AWS Lambda

Build AWS Lambda deployment packages and layers for multiple Python versions (3.10+) and architectures (x86_64/arm64).

[![Dependabot Updates](https://github.com/fok666/lambda-python-layer/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/fok666/lambda-python-layer/actions/workflows/dependabot/dependabot-updates) [![Build and Release Multi-Arch Docker Images](https://github.com/fok666/lambda-python-layer/actions/workflows/build-and-release.yml/badge.svg)](https://github.com/fok666/lambda-python-layer/actions/workflows/build-and-release.yml)

Inspired by [LambdaZipper](https://github.com/tiivik/LambdaZipper)

## Features

- 🐍 **Multiple Python versions**: Support for Python 3.10, 3.11, 3.12, 3.13, and 3.14 (default)
- 🏗️ **Multi-architecture**: Build for both x86_64 (amd64) and arm64 (aarch64) by default
- 📦 **Bulk packaging**: Uses `requirements.txt` by default to package multiple dependencies
- 🔄 **Two output formats**: Single combined archive (default) or individual archives per package
- ⚡ **Fast builds**: Based on Amazon Linux 2023 for compatibility with Lambda runtime
- 🚀 **Zero-config**: Run without arguments for sensible defaults

## Quick Start

### Default Usage (Recommended)

Simply run the build script with no arguments:

```bash
./build-multiarch.sh
```

**Default behavior:**
- Uses Python 3.14 (latest)
- Reads from `requirements.txt` in the current directory
- Builds for both x86_64 and arm64 architectures
- Creates single combined archive per architecture
- Automatically uses the correct Amazon Linux version for Lambda compatibility

**Result**: `combined-python3.14-x86_64.zip` and `combined-python3.14-aarch64.zip` in `./output/`

> **Note**: This tool uses Amazon Linux 2 for Python 3.10-3.11 and Amazon Linux 2023 for Python 3.12+ to ensure compatibility with [AWS Lambda Python runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html).

### Customizing the Build

```bash
# Use a specific Python version
./build-multiarch.sh --python 3.13

# Build only for x86_64
./build-multiarch.sh --skip-arm64

# Create individual archives per package
./build-multiarch.sh --individual

# Build a single package instead of requirements.txt
./build-multiarch.sh --package numpy

# Combine options
./build-multiarch.sh --python 3.12 --skip-arm64 --individual
```

## Command Reference

### build-multiarch.sh Options

| Option | Description | Default |
|--------|-------------|---------|
| `--python VERSION` | Python version (3.10-3.14) | 3.14 |
| `-r, --requirements FILE` | Path to requirements.txt | requirements.txt |
| `--package NAME` | Single package name (overrides requirements.txt) | - |
| `--skip-x86`, `--skip-amd64` | Skip x86_64 architecture build | Build both |
| `--skip-arm64` | Skip arm64 architecture build | Build both |
| `--individual` | Create individual archives per package | Single combined |
| `--image NAME` | Custom Docker image name | lambda-zipper |
| `--help` | Show help message | - |

### Usage Examples

```bash
# Default: Python 3.14, requirements.txt, multi-arch, combined archive
./build-multiarch.sh

# Use different Python version
./build-multiarch.sh --python 3.13

# Build only for x86_64 architecture
./build-multiarch.sh --skip-arm64

# Create individual archives for each package
./build-multiarch.sh --individual

# Use custom requirements file
./build-multiarch.sh -r ./my-requirements.txt

# Build a single package (ignores requirements.txt)
./build-multiarch.sh --package numpy

# Combine multiple options
./build-multiarch.sh --python 3.12 --skip-arm64 --individual -r prod-requirements.txt
```

## Advanced Usage

### Manual Docker Build (Lower-Level)

For direct Docker control, you can build and run containers manually:

#### Single Package Mode

Build a Docker image:
```bash
docker build --build-arg PYTHON_VERSION=3.14 -t lambda-zipper .
```

Package a single library:
```bash
docker run --rm -v $(pwd)/output:/package lambda-zipper numpy
```

#### Requirements.txt with Individual Archives

```bash
docker run --rm \
  -v $(pwd)/requirements.txt:/input/requirements.txt \
  -v $(pwd)/output:/package \
  lambda-zipper
```

#### Requirements.txt with Combined Archive

```bash
docker run --rm \
  -e SINGLE_FILE=true \
  -v $(pwd)/requirements.txt:/input/requirements.txt \
  -v $(pwd)/output:/package \
  lambda-zipper
```

## Supported Python Versions

This project automatically uses the appropriate Amazon Linux version based on [AWS Lambda Python runtime requirements](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html):

| Python Version | Base OS | Installation Method | Lambda Runtime Compatibility |
|----------------|---------|---------------------|------------------------------|
| 3.10           | Amazon Linux 2 | Built from source | ✅ python3.10 runtime |
| 3.11           | Amazon Linux 2 | Built from source | ✅ python3.11 runtime |
| 3.12           | Amazon Linux 2023 | dnf package | ✅ python3.12 runtime |
| 3.13           | Amazon Linux 2023 | dnf package | ✅ python3.13 runtime |
| 3.14           | Amazon Linux 2023 | Built from source | ⚙️ Future runtime (Default) |

**Key Points:**
- **Python 3.10 & 3.11**: Use Amazon Linux 2 (matches Lambda runtime environment)
- **Python 3.12 & 3.13**: Use Amazon Linux 2023 (matches Lambda runtime environment)
- **Python 3.14**: Uses Amazon Linux 2023, compiled from source for latest features
- All versions are built with development headers for compiling binary packages

## Output Formats

### Lambda Layer Format
```
python/
  lib/
    pythonX.Y/
      site-packages/
        [your packages here]
```
Upload as a Lambda Layer in the AWS Console.

### Flat Deployment Format
```
[your packages at root level]
```
Extract into your Lambda deployment package alongside your code.

## Architecture Support

- **x86_64 (amd64)**: Standard Lambda runtime
- **arm64 (aarch64)**: AWS Graviton2 Lambda runtime (cost-effective)

Choose the architecture that matches your Lambda function configuration.

## Real-World Examples

### Data Science Stack

Create `requirements.txt`:
```txt
numpy==1.26.4
pandas==2.1.4
scipy==1.11.4
scikit-learn==1.3.2
```

Build with defaults (Python 3.14, multi-arch, combined archive):
```bash
./build-multiarch.sh
```

**Result**: `combined-python3.14-x86_64.zip` and `combined-python3.14-aarch64.zip` ready for Lambda Layer

### Web Scraping Stack

Create `requirements.txt`:
```txt
requests==2.31.0
beautifulsoup4==4.12.2
lxml==4.9.3
```

Build for Python 3.13, x86_64 only:
```bash
./build-multiarch.sh --python 3.13 --skip-arm64
```

### Computer Vision with OpenCV

Create `requirements.txt`:
```txt
Pillow==10.2.0
opencv-python-headless==4.9.0.80
numpy==1.26.4
```

Build individual archives for selective deployment:
```bash
./build-multiarch.sh --individual
```

**Result**: Separate archives for each package, allowing you to pick and choose

### AWS SDK Only (Single Package)

Build only boto3 for both architectures:
```bash
./build-multiarch.sh --package boto3
```

**Result**: `boto3-python3.14-x86_64.zip` and `boto3-python3.14-aarch64.zip`

### Legacy Python Version Support

Build for Python 3.10 with specific requirements:
```bash
./build-multiarch.sh --python 3.10 -r legacy-requirements.txt
```

## Project Structure

```
.
├── Dockerfile.al2         # Amazon Linux 2 image (Python 3.10-3.11)
├── Dockerfile.al2023      # Amazon Linux 2023 image (Python 3.12-3.14)
├── Dockerfile             # Default (points to AL2023)
├── package.sh             # Packaging script with requirements.txt support
├── build-multiarch.sh     # Helper script for multi-arch builds
├── requirements.example.txt
└── readme.md
```

## How It Works

1. **Base Image Selection**: Automatically chooses Amazon Linux 2 (for Python 3.10-3.11) or Amazon Linux 2023 (for Python 3.12+) to match AWS Lambda runtime environments
2. **Python Installation**: Installs specified Python version (3.10-3.14) with development headers
3. **Package Installation**: Uses pip with `--target` flag to install packages with proper dependencies
4. **Packaging**: Creates zip archives with proper Lambda Layer structure (`python/lib/pythonX.Y/site-packages/`)
5. **Multi-arch**: Leverages Docker buildx for platform-specific builds (x86_64 and arm64)
6. **Runtime Compatibility**: Ensures binary compatibility with AWS Lambda execution environments

## Troubleshooting

### Docker buildx not available
Enable buildx in Docker Desktop settings or install manually:
```bash
docker buildx version
```

### Requirements file not found
By default, the script looks for `requirements.txt` in the current directory. Specify a different file:
```bash
./build-multiarch.sh -r path/to/my-requirements.txt
```

### Package has binary dependencies
The build includes gcc, g++, and cmake for compiling binary extensions. Most packages should work, but some may require additional system libraries. Modify the Dockerfile to add specific dependencies.

### Lambda Layer size limits
Lambda has a 250MB (unzipped) limit for layers. For large packages:
- Use `--individual` flag to split packages into separate archives
- Deploy multiple smaller layers
- Use Lambda deployment package directly
- Consider AWS Lambda Extensions or Container Images

### Build takes too long
Python 3.14 is compiled from source and takes longer. For faster builds:
- Use Python 3.13 or earlier: `./build-multiarch.sh --python 3.13`
- Build only one architecture: `./build-multiarch.sh --skip-arm64`
- Docker caches layers, so subsequent builds are faster

## Advanced Docker Usage

### Custom Dockerfile Modifications

Add system dependencies:
```dockerfile
# Add after the base install in Dockerfile
RUN dnf -y install postgresql-devel libxml2-devel
```

### Building Without the Helper Script

```bash
# Build for specific platform
docker buildx build \
  --platform linux/amd64 \
  --build-arg PYTHON_VERSION=3.14 \
  -t lambda-zipper:custom \
  --load .

# Run with requirements (combined archive)
docker run --rm \
  -e SINGLE_FILE=true \
  -v $(pwd)/requirements.txt:/input/requirements.txt \
  -v $(pwd)/output:/package \
  lambda-zipper:custom

# Run with single package
docker run --rm \
  -v $(pwd)/output:/package \
  lambda-zipper:custom numpy
```

## Output File Naming

Archives are named with the following pattern:

**Combined archives** (default):
- `combined-python{VERSION}-{ARCH}.zip`
- Example: `combined-python3.14-x86_64.zip`, `combined-python3.14-aarch64.zip`

**Individual package archives** (with `--individual`):
- `{PACKAGE}-python{VERSION}-{ARCH}.zip`
- Example: `numpy-python3.14-x86_64.zip`, `requests-python3.13-aarch64.zip`

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is open source and available for use and modification.
