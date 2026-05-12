# Team Nexus mise runtime integration.
#
# Hermes' terminal backend captures a login-shell environment snapshot. Debian's
# /etc/profile resets PATH for non-root login shells, so Dockerfile ENV PATH alone
# is not enough to keep mise-managed toolchains visible to agent terminal calls.
# Keep mise shims on PATH for every login shell so future mise-installed CLIs work
# without per-tool symlinks into /usr/local/bin.

export MISE_DATA_DIR="${MISE_DATA_DIR:-/opt/mise}"
export MISE_CACHE_DIR="${MISE_CACHE_DIR:-/opt/mise/cache}"
export MISE_CONFIG_DIR="${MISE_CONFIG_DIR:-/etc/mise}"
export MISE_INSTALL_PATH="${MISE_INSTALL_PATH:-/usr/local/bin/mise}"

case ":$PATH:" in
  *:/opt/mise/shims:*) ;;
  *) export PATH="/opt/mise/shims:$PATH" ;;
esac
