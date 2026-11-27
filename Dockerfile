# syntax=docker/dockerfile:1.7
#
# One image with everything: the MCP server, Remotion (Node + Chromium), Blender and ffmpeg.
# The container is the sandbox: code the agent writes (Remotion TSX, Blender Python) runs
# here and can only see the /work volume.

ARG PYTHON_VERSION=3.12
ARG NODE_VERSION=22

# --- Remotion toolchain, from the committed lockfile --------------------------------------
FROM node:${NODE_VERSION}-bookworm-slim AS node

FROM node AS render-deps
WORKDIR /render
COPY render/package.json render/package-lock.json ./
RUN npm ci --omit=dev

# --- Blender, verified against the checksum from blender.org -------------------------------
# Official Linux builds exist for x86_64 only; on arm64 (Apple Silicon) the image is built
# without Blender and the render_blender tool says so. Bump the version and the checksum
# together (blender.org publishes blender-<version>.sha256 next to each release).
FROM debian:bookworm-slim AS blender
ARG TARGETARCH
ARG BLENDER_VERSION=5.3.0
ARG BLENDER_SHA256=dacb8264197a3f7fda6001285a5a506fc97ee943881261c2c3bd63c882f22e05
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*
RUN set -eux; mkdir -p /opt/blender; \
    if [ "$TARGETARCH" = "amd64" ]; then \
      curl -fsSL -o /tmp/blender.tar.xz \
        "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}-linux-x64.tar.xz"; \
      echo "${BLENDER_SHA256}  /tmp/blender.tar.xz" | sha256sum -c -; \
      tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1; \
    else \
      echo "No official Blender build for ${TARGETARCH}; skipping."; \
    fi

# --- Final image -------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg chromium fonts-liberation fonts-noto-color-emoji ca-certificates \
      libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libxext6 libx11-6 \
      libsm6 libgl1 libegl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=render-deps /render/node_modules /opt/render/node_modules
COPY --from=blender /opt/blender /opt/blender
RUN if [ -x /opt/blender/blender ]; then ln -s /opt/blender/blender /usr/local/bin/blender; fi

# Chromium refuses to run as a normal user without its own sandbox unless the container
# provides the isolation. It does, so the wrapper turns Chromium's sandbox off.
RUN printf '#!/bin/sh\nexec /usr/bin/chromium --no-sandbox --disable-dev-shm-usage "$@"\n' \
      > /usr/local/bin/chromium-container \
    && chmod 0755 /usr/local/bin/chromium-container

# Python dependencies come from hash-locked files (requirements.txt, requirements-build.txt):
# a changed or substituted package fails the build instead of being installed.
WORKDIR /app
COPY requirements.txt requirements-build.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt -r requirements-build.txt
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps --no-build-isolation .

RUN useradd --create-home --uid 1000 clapper && mkdir /work && chown clapper /work
USER clapper

LABEL org.opencontainers.image.title="clapper" \
      org.opencontainers.image.description="MCP server that lets an AI agent make videos (Remotion, Blender, voice-over, captions)" \
      org.opencontainers.image.licenses="MIT"

ENV CLAPPER_WORK=/work \
    CLAPPER_RENDER_MODULES=/opt/render/node_modules \
    CLAPPER_CHROMIUM=/usr/local/bin/chromium-container \
    CLAPPER_PORT=8770 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    PYTHONUNBUFFERED=1

WORKDIR /work
VOLUME /work
EXPOSE 8770

# Only meaningful in HTTP mode; in stdio mode there is nothing to probe, so it passes.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,sys,urllib.request as u; \
os.getenv('CLAPPER_TRANSPORT')!='http' or u.urlopen('http://127.0.0.1:%s/healthz'%os.getenv('CLAPPER_PORT','8770'),timeout=3)"

ENTRYPOINT ["clapper"]
