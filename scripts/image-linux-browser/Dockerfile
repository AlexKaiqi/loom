# linux-browser-v1 build input (amendment-linux-browser-2026-09-15).
# Identity = the final image digest (A1-④); resolved package versions are
# recorded in the build manifest, not treated as identity.
FROM python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG PLAYWRIGHT_VERSION=1.62.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium fonts-liberation ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "playwright==${PLAYWRIGHT_VERSION}"
