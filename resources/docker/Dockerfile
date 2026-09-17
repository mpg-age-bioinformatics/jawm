# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.13-slim-bookworm
FROM ${PYTHON_IMAGE}

LABEL org.opencontainers.image.description="Generic runtime image for jawm workflows" \
      org.opencontainers.image.documentation="https://bioinformatics.age.mpg.de/jawm/" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/mpg-age-bioinformatics/jawm" \
      org.opencontainers.image.title="jawm"

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install common workflow utilities and the Docker CLI. The Docker daemon is
# intentionally not included; mount a trusted daemon socket when Docker-backed
# processes are required.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        coreutils \
        curl \
        git \
        gzip \
        openssh-client \
        procps \
        tar \
        unzip; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc; \
    chmod a+r /etc/apt/keyrings/docker.asc; \
    . /etc/os-release; \
    printf '%s\n' \
        'Types: deb' \
        'URIs: https://download.docker.com/linux/debian' \
        "Suites: ${VERSION_CODENAME}" \
        'Components: stable' \
        "Architectures: $(dpkg --print-architecture)" \
        'Signed-By: /etc/apt/keyrings/docker.asc' \
        > /etc/apt/sources.list.d/docker.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends docker-ce-cli; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/jawm

# Copy only the package inputs needed for installation. Build-specific and
# repository-local files are not included in the installed source tree.
COPY pyproject.toml README.md ./
COPY jawm ./jawm

RUN python -m pip install ".[full]" \
    && jawm --version \
    && docker --version

# Keep the image definition available for inspection and documentation.
COPY resources/docker/Dockerfile /usr/share/doc/jawm/Dockerfile

WORKDIR /workspace

CMD ["jawm", "--help"]
