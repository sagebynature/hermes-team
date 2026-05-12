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
    AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium \
    PATH=/opt/mise/shims:/opt/data/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      chromium \
      git \
      gnupg \
      docker.io \
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

# Docker CLI is used by the Kanban dispatcher sidecar through the mounted host
# Docker socket. Install Compose v2 as a Docker CLI plugin so `docker compose`
# works consistently inside the dispatcher container.
RUN set -eux; \
    case "$(uname -m)" in \
      x86_64) compose_arch="x86_64" ;; \
      aarch64|arm64) compose_arch="aarch64" ;; \
      *) echo "Unsupported architecture for docker compose plugin: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    mkdir -p /usr/local/lib/docker/cli-plugins; \
    curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-${compose_arch}" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose; \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose; \
    docker --version; \
    docker compose version

RUN curl -fsSL https://mise.run | sh \
    && mise --version \
    && mkdir -p /etc/mise /opt/mise/cache /workspace

# Global defaults. Individual agents can override with /workspace/.mise.toml
# or mounted config under /opt/data if desired.
COPY docker/mise/config.toml /etc/mise/config.toml

# Preinstall lightweight/common runtimes that MCP servers and startup agents often need.
# If you want a smaller image, remove these and let agents install from their workspace .mise.toml.
RUN mise trust /etc/mise/config.toml \
    && mise install --yes \
    && mise reshim

# Install uv/uvx directly instead of through mise's aqua backend. The mise uv
# plugin verifies GitHub artifact attestations, and uv releases can fail Docker
# builds when that attestation metadata is missing or not in the expected
# workflow shape. Astral's installer keeps uv available for Hermes and MCP
# tooling without making the whole image build depend on mise/aqua attestation.
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && uv --version \
    && uvx --version

# Install repo script dependencies into system Python because runtime services call
# scripts/*.py with python3 from the bind-mounted /workspace checkout.
COPY requirements.txt /tmp/team-nexus-python-requirements.txt
RUN uv pip install --system --break-system-packages --python /usr/bin/python3 --no-cache -r /tmp/team-nexus-python-requirements.txt \
    && rm -f /tmp/team-nexus-python-requirements.txt \
    && rm -rf /root/.cache/uv /tmp/uv-cache

# Install voice extras into the upstream Hermes venv for CLI/gateway voice mode.
# The upstream Docker image installs Hermes as site-packages; Hermes doctor still
# checks for a source-tree-style PROJECT_ROOT/.venv/bin/hermes. Add a small
# compatibility shim so doctor reflects the working runtime entry point.
RUN cd /opt/hermes \
    && uv pip install --no-cache --python /opt/hermes/.venv/bin/python '.[voice]' \
    && ln -sfn /opt/hermes/.venv/bin/hermes /usr/local/bin/hermes \
    && site_packages="$(/opt/hermes/.venv/bin/python -c 'import site; print(site.getsitepackages()[0])')" \
    && mkdir -p "$site_packages/.venv/bin" \
    && ln -sfn /opt/hermes/.venv/bin/hermes "$site_packages/.venv/bin/hermes" \
    && rm -rf /root/.cache/uv /tmp/uv-cache

# Install local browser automation support for Hermes' browser toolset. Chromium
# comes from apt because Chrome for Testing does not publish Linux ARM64 builds.
# Also install the Google Workspace CLI (`gws`) for shared Workspace skills.
RUN npm install -g agent-browser @googleworkspace/cli \
    && ln -sfn /opt/hermes/node_modules/.bin/agent-browser /usr/local/bin/agent-browser \
    && ln -sfn "$(mise which gws)" /usr/local/bin/gws \
    && command -v gws \
    && gws --version \
    && npm cache clean --force

# Install Hermes' bundled RL backend when the upstream image contains the
# tinker-atropos submodule. Doctor checks for this package in every agent.
RUN if [ -d /opt/hermes/tinker-atropos ]; then \
      uv pip install --no-cache --python /opt/hermes/.venv/bin/python -e /opt/hermes/tinker-atropos; \
      site_packages="$(/opt/hermes/.venv/bin/python -c 'import site; print(site.getsitepackages()[0])')"; \
      ln -sfn /opt/hermes/tinker-atropos "$site_packages/tinker-atropos"; \
    fi \
    && rm -rf /root/.cache/uv /tmp/uv-cache

COPY docker/team-nexus-entrypoint.sh /usr/local/bin/team-nexus-entrypoint.sh
RUN chmod +x /usr/local/bin/team-nexus-entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/team-nexus-entrypoint.sh"]

WORKDIR /workspace
