FROM nousresearch/hermes-agent:latest

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# mise-en-place: language/tool version manager for agent workspaces and MCP runtimes.
# Keep mise itself in the image, while letting each mounted /workspace provide its own .mise.toml.
ENV MISE_DATA_DIR=/opt/mise \
    MISE_CACHE_DIR=/opt/mise/cache \
    MISE_CONFIG_DIR=/etc/mise \
    MISE_INSTALL_PATH=/usr/local/bin/mise \
    MISE_YES=1 \
    PATH=/opt/mise/shims:/opt/data/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      git \
      gnupg \
      ffmpeg \
      jq \
      libopus0 \
      openssh-client \
      pkg-config \
      portaudio19-dev \
      ripgrep \
      tar \
      unzip \
      xz-utils \
      zip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://mise.run | sh \
    && mise --version \
    && mkdir -p /etc/mise /opt/mise/cache /workspace

# Global defaults. Individual agents can override with /workspace/.mise.toml
# or mounted config under /opt/data if desired.
COPY mise/config.toml /etc/mise/config.toml

# Preinstall lightweight/common runtimes that MCP servers and startup agents often need.
# If you want a smaller image, remove these and let agents install from their workspace .mise.toml.
RUN mise trust /etc/mise/config.toml \
    && mise install --yes \
    && mise reshim

# Install voice extras into the upstream Hermes venv for CLI/gateway voice mode.
RUN cd /opt/hermes \
    && uv pip install --no-cache --python /opt/hermes/.venv/bin/python '.[voice]' \
    && rm -rf /root/.cache/uv /tmp/uv-cache

# Install Hermes' bundled RL backend when the upstream image contains the
# tinker-atropos submodule. Doctor checks for this package in every agent.
RUN if [ -d /opt/hermes/tinker-atropos ]; then \
      uv pip install --no-cache --python /opt/hermes/.venv/bin/python -e /opt/hermes/tinker-atropos; \
    fi \
    && rm -rf /root/.cache/uv /tmp/uv-cache

COPY team-nexus-entrypoint.sh /usr/local/bin/team-nexus-entrypoint.sh
RUN chmod +x /usr/local/bin/team-nexus-entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/team-nexus-entrypoint.sh"]

WORKDIR /workspace
