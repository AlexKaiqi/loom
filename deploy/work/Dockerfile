# Build toolchains never enter the deployed shared Work facility.
FROM golang@sha256:3b4a11519ad929d1e1d261a12cff056f0c85b735253d7d861346b9c6f8b36437 AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf bison flex g++ git libprotobuf-dev libnl-route-3-dev libtool make pkg-config protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*
RUN git init /tmp/nsjail && git -C /tmp/nsjail remote add origin https://github.com/google/nsjail.git \
    && git -C /tmp/nsjail fetch --depth=1 origin f78475530b46d0186111a9096b30725f816b55fe \
    && git -C /tmp/nsjail checkout --detach FETCH_HEAD \
    && git -C /tmp/nsjail submodule update --init --depth=1 \
    && make -C /tmp/nsjail -j2 \
    && install /tmp/nsjail/nsjail /usr/local/bin/nsjail \
    && git -C /tmp/nsjail submodule status > /usr/local/share/loom-nsjail-submodules.lock \
    && rm -rf /tmp/nsjail
COPY runtime/go.mod runtime/go.sum /build/
RUN cd /build && go mod download
COPY runtime /build
RUN cd /build && CGO_ENABLED=0 go build -trimpath -o /usr/local/bin/loom-runtime ./cmd/loom

FROM node@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6
RUN apt-get update && apt-get install -y --no-install-recommends \
    git python3 python3-venv sqlite3 acl ca-certificates libprotobuf32 libnl-route-3-200 \
    && rm -rf /var/lib/apt/lists/*
COPY harnesses/kernel/requirements.lock /tmp/loom-requirements.lock
RUN python3 -m venv /usr/local/loom-python && /usr/local/loom-python/bin/pip install --no-cache-dir --require-hashes -r /tmp/loom-requirements.lock && rm /tmp/loom-requirements.lock
COPY services/model/package.json services/model/package-lock.json /opt/loom/services/model/
RUN cd /opt/loom/services/model && npm ci --omit=dev --no-audit --no-fund && npm cache clean --force
COPY services/model /opt/loom/services/model
COPY harnesses /opt/loom/harnesses
COPY templates /opt/loom/templates
COPY deploy /opt/loom/deploy
COPY docs/loom-design-book.html /opt/loom/docs/loom-design-book.html
COPY --from=build /usr/local/bin/nsjail /usr/local/bin/nsjail
COPY --from=build /usr/local/bin/loom-runtime /usr/local/bin/loom-runtime
COPY --from=build /usr/local/share/loom-nsjail-submodules.lock /usr/local/share/loom-nsjail-submodules.lock
RUN mkdir -p /opt/loom/bin && printf '#!/bin/sh\nexec node /opt/loom/services/model/worker.mjs "$@"\n' > /opt/loom/bin/loom-model && chmod 755 /opt/loom/bin/loom-model \
    && dpkg-query -W > /usr/local/share/loom-work-packages.lock
ENV HOME=/var/lib/loom-host LOOM_INSTALL_ROOT=/opt/loom LOOM_EXECUTION_CONFIG=/run/loom/execution.toml
ENV PATH="/opt/loom/bin:/usr/local/loom-python/bin:${PATH}"
ENTRYPOINT ["/opt/loom/deploy/work/entrypoint.sh"]
