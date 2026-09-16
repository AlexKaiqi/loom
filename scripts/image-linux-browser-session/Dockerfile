# 2026-09-15 linux-browser session image (amendment-linux-browser-2026-09-15 ④a).
# Base = the frozen session environment image (node/pi closure arrives as the
# runtime readonly deps volume, not image layers — /opt manifest is unchanged).
# This image adds only chromium + playwright so the session harness can drive
# browser tasks. Failure never replaces any registered profile (A1-②).
# The base digest pin is enforced by build.sh's pre-build inspect check (a bare
# sha256: FROM would make Docker attempt a registry pull); the tag is local only.
FROM lore-validation:2026-09-14

ARG CHROMIUM_VERSION
ARG PLAYWRIGHT_VERSION=1.62.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      chromium fonts-liberation ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "playwright==${PLAYWRIGHT_VERSION}"
