ARG PYTHON_VERSION=3.13
FROM amazonlinux:2023

# Install base dependencies
RUN dnf -y install git zip tar gzip gcc gcc-c++ cmake \
    wget openssl-devel bzip2-devel libffi-devel \
    zlib-devel xz-devel sqlite-devel readline-devel xz && \
    dnf clean all

# Accept Python version as build arg (supports 3.10, 3.11, 3.12, 3.13, 3.14)
ARG PYTHON_VERSION

# Install Python - either from dnf or build from source
RUN if dnf list available python${PYTHON_VERSION} 2>/dev/null; then \
        echo "Installing Python ${PYTHON_VERSION} from dnf..."; \
        dnf -y install python${PYTHON_VERSION} python${PYTHON_VERSION}-pip python${PYTHON_VERSION}-devel && \
        dnf clean all; \
    else \
        echo "Building Python ${PYTHON_VERSION} from source..."; \
        cd /tmp && \
        wget https://www.python.org/ftp/python/${PYTHON_VERSION}.0/Python-${PYTHON_VERSION}.0.tar.xz && \
        tar xf Python-${PYTHON_VERSION}.0.tar.xz && \
        cd Python-${PYTHON_VERSION}.0 && \
        ./configure --enable-optimizations --with-ensurepip=install && \
        make -j$(nproc) && \
        make altinstall && \
        cd / && \
        rm -rf /tmp/Python-${PYTHON_VERSION}.0*; \
    fi

# Create symlink for easier access
RUN if [ -f /usr/local/bin/python${PYTHON_VERSION} ]; then \
        ln -sf /usr/local/bin/python${PYTHON_VERSION} /usr/local/bin/python3; \
        ln -sf /usr/local/bin/pip${PYTHON_VERSION} /usr/local/bin/pip3; \
    elif [ -f /usr/bin/python${PYTHON_VERSION} ]; then \
        ln -sf /usr/bin/python${PYTHON_VERSION} /usr/local/bin/python3; \
        ln -sf /usr/bin/pip${PYTHON_VERSION} /usr/local/bin/pip3; \
    fi

# Upgrade pip (skip if pip not available as module)
RUN python3 -m pip install --upgrade pip 2>/dev/null || \
    python3 -m ensurepip && python3 -m pip install --upgrade pip

ADD package.sh /
RUN chmod +x /package.sh

ENTRYPOINT ["/package.sh"]