# Layer Build & Docker Style Guide

## General
- This project focuses on building AWS Lambda Layers.
- Consistency between the build environment (Docker) and the runtime environment (AWS Lambda) is critical.

## Shell Scripting (Build Scripts)
- Scripts like `build-multiarch.sh` and `package.sh` should be robust.
- Use `set -e` to fail immediately if a build step fails.
- Echo clear status messages to the console during long build processes.
- Handle architecture differences (x86_64 vs arm64) explicitly.

## Docker
- Use Amazon Linux 2 or Amazon Linux 2023 base images to match Lambda runtimes.
- Avoid installing unnecessary tools in the final layer output.
- Ensure the output directory structure matches Lambda requirements exactly (`python/lib/pythonX.Y/site-packages`).

## Python Dependencies
- Use `requirements.txt` with pinned versions for reproducibility.
- Separate build dependencies from runtime dependencies if necessary.
