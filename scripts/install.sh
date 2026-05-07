#!/usr/bin/env bash
# ============================================================================
# Team Nexus Installer
# ============================================================================
# Guided bootstrap for the Team Nexus profile-driven Hermes runtime.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/sagebynature/team-nexus/main/scripts/install.sh | bash
#
# Or with options:
#   curl -fsSL ... | bash -s -- --dir ~/team-nexus --skip-up
#
# This script is intentionally conservative with secrets and runtime state:
# - It will not overwrite .env, runtime/, auth, sessions, memory, logs, or Kanban DBs.
# - It guides the user through editing .env instead of asking them to paste secrets
#   into the install transcript.
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

REPO_URL_HTTPS="${TEAM_NEXUS_REPO_URL:-https://github.com/sagebynature/team-nexus.git}"
REPO_URL_SSH="${TEAM_NEXUS_REPO_SSH:-git@github.com:sagebynature/team-nexus.git}"
BRANCH="${TEAM_NEXUS_BRANCH:-main}"
INSTALL_DIR="${TEAM_NEXUS_INSTALL_DIR:-$HOME/team-nexus}"
RUN_PREFLIGHT=true
RUN_BUILD=true
RUN_UP=true
EDIT_ENV=true
ASSUME_YES=false
PYTHON_CMD="python3"

if [ -t 0 ]; then
    IS_INTERACTIVE=true
else
    IS_INTERACTIVE=false
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --repo-url)
            REPO_URL_HTTPS="$2"
            shift 2
            ;;
        --skip-preflight)
            RUN_PREFLIGHT=false
            shift
            ;;
        --skip-build)
            RUN_BUILD=false
            shift
            ;;
        --skip-up)
            RUN_UP=false
            shift
            ;;
        --no-edit-env)
            EDIT_ENV=false
            shift
            ;;
        -y|--yes)
            ASSUME_YES=true
            shift
            ;;
        -h|--help)
            echo "Team Nexus Installer"
            echo ""
            echo "Usage: install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dir PATH          Install/update checkout at PATH (default: ~/team-nexus)"
            echo "  --branch NAME       Git branch to install (default: main)"
            echo "  --repo-url URL      HTTPS git repo URL override"
            echo "  --skip-preflight    Skip make preflight"
            echo "  --skip-build        Skip docker image build"
            echo "  --skip-up           Do not start services after setup"
            echo "  --no-edit-env       Create .env if missing, but do not open an editor"
            echo "  -y, --yes           Accept default prompts where safe"
            echo "  -h, --help          Show this help"
            echo ""
            echo "Example:"
            echo "  curl -fsSL https://raw.githubusercontent.com/sagebynature/team-nexus/main/scripts/install.sh | bash"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

if [ "$ASSUME_YES" = true ]; then
    EDIT_ENV=false
fi

print_banner() {
    echo ""
    echo -e "${MAGENTA}${BOLD}"
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│              Team Nexus Installer                       │"
    echo "├─────────────────────────────────────────────────────────┤"
    echo "│  Hermes-native AI software delivery team runtime.       │"
    echo "└─────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
}

log_info() { echo -e "${CYAN}→${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

has_tty() {
    (: </dev/tty) 2>/dev/null
}

prompt_yes_no() {
    local question="$1"
    local default="${2:-yes}"
    local answer=""
    local suffix="[Y/n]"

    case "$default" in
        [nN]|[nN][oO]|false|0) suffix="[y/N]" ;;
    esac

    if [ "$ASSUME_YES" = true ]; then
        case "$default" in
            [nN]|[nN][oO]|false|0) return 1 ;;
            *) return 0 ;;
        esac
    fi

    if [ "$IS_INTERACTIVE" = true ]; then
        read -r -p "$question $suffix " answer || answer=""
    elif has_tty && [ -w /dev/tty ]; then
        printf "%s %s " "$question" "$suffix" > /dev/tty
        IFS= read -r answer < /dev/tty || answer=""
    else
        answer=""
    fi

    answer="${answer#"${answer%%[![:space:]]*}"}"
    answer="${answer%"${answer##*[![:space:]]}"}"

    if [ -z "$answer" ]; then
        case "$default" in
            [nN]|[nN][oO]|false|0) return 1 ;;
            *) return 0 ;;
        esac
    fi

    case "$answer" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

print_step() {
    echo ""
    echo -e "${BLUE}${BOLD}Step $1:${NC} ${BOLD}$2${NC}"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

python_has_pyyaml() {
    "$PYTHON_CMD" - <<'PY' >/dev/null 2>&1
import yaml
PY
}

bootstrap_python_deps() {
    cd "$INSTALL_DIR"

    if python_has_pyyaml || command_exists ruby; then
        if python_has_pyyaml; then
            log_success "Python YAML support available"
        else
            log_success "Ruby YAML fallback available"
        fi
        return 0
    fi

    log_warn "PyYAML is not installed and Ruby is unavailable; bootstrapping local Python dependencies."
    if [ ! -x .venv/bin/python ]; then
        "$PYTHON_CMD" -m venv .venv
    fi

    .venv/bin/python -m pip install --upgrade pip >/dev/null
    .venv/bin/python -m pip install PyYAML >/dev/null
    PYTHON_CMD="$INSTALL_DIR/.venv/bin/python"

    if python_has_pyyaml; then
        log_success "Installed PyYAML into $INSTALL_DIR/.venv"
    else
        log_error "Could not install PyYAML into $INSTALL_DIR/.venv"
        echo "Install PyYAML or Ruby, then re-run this installer:"
        echo "  $PYTHON_CMD -m pip install PyYAML"
        exit 1
    fi
}

open_editor() {
    local file="$1"
    local editor="${EDITOR:-}"

    if [ -z "$editor" ]; then
        if command_exists nano; then
            editor="nano"
        elif command_exists vim; then
            editor="vim"
        elif command_exists vi; then
            editor="vi"
        else
            return 1
        fi
    fi

    if [ "$IS_INTERACTIVE" = true ]; then
        "$editor" "$file"
    elif has_tty; then
        "$editor" "$file" < /dev/tty > /dev/tty
    else
        return 1
    fi
}

print_plan() {
    echo "This installer will guide you through a complete Team Nexus setup:"
    echo ""
    echo "  1. Check host prerequisites: git, make, python3 with venv support, Docker, Docker Compose"
    echo "  2. Clone or update the Team Nexus repo"
    echo "  3. Create .env from .env.example without overwriting secrets"
    echo "  4. Help you edit .env for model provider and Atlas Discord settings"
    echo "  5. Render Hermes profile homes into ignored runtime state"
    echo "  6. Run preflight validation"
    echo "  7. Build the shared Team Nexus Hermes Docker image"
    echo "  8. Start Atlas gateway, dashboard, and mission notifier"
    echo "  9. Print dashboard, logs, doctor, and Kanban smoke-test commands"
    echo ""
    echo "Chosen checkout: $INSTALL_DIR"
    echo "Branch:          $BRANCH"
    echo "Repo:            $REPO_URL_HTTPS"
    echo ""

    if has_tty; then
        if ! prompt_yes_no "Continue?" "yes"; then
            log_info "Install cancelled before making changes."
            exit 0
        fi
    else
        log_warn "No terminal available for prompts; continuing with safe defaults."
        EDIT_ENV=false
        RUN_UP=false
    fi
}

check_os() {
    case "$(uname -s)" in
        Linux*) OS="linux" ;;
        Darwin*) OS="macos" ;;
        *) OS="unknown" ;;
    esac
    log_success "Detected host: $OS ($(uname -m))"
}

require_prerequisites() {
    local missing=()

    command_exists git || missing+=("git")
    command_exists make || missing+=("make")
    command_exists python3 || missing+=("python3")
    if command_exists python3 && ! python3 -m venv --help >/dev/null 2>&1; then
        missing+=("python3 venv module")
    fi

    if ! command_exists docker; then
        missing+=("docker")
    elif ! docker compose version >/dev/null 2>&1; then
        missing+=("docker compose plugin")
    fi

    if [ ${#missing[@]} -eq 0 ]; then
        log_success "Required commands found"
        log_info "$(git --version)"
        log_info "$(python3 --version 2>&1)"
        log_info "$(docker --version 2>/dev/null || true)"
        log_info "$(docker compose version 2>/dev/null || true)"
        return 0
    fi

    log_error "Missing required prerequisite(s): ${missing[*]}"
    echo ""
    echo "Install them, then re-run this installer. Suggested commands:"
    case "$OS" in
        macos)
            echo "  xcode-select --install        # Git/make if missing"
            echo "  brew install python docker    # or install Docker Desktop from docker.com"
            ;;
        linux)
            echo "  sudo apt update && sudo apt install -y git make python3 python3-venv docker.io docker-compose-plugin"
            echo "  sudo usermod -aG docker \$USER  # then log out/in if Docker needs permissions"
            ;;
        *)
            echo "  Install git, make, python3, Docker, and Docker Compose for your platform."
            ;;
    esac
    exit 1
}

check_docker_running() {
    if docker info >/dev/null 2>&1; then
        log_success "Docker daemon is running"
        return 0
    fi

    log_error "Docker is installed but the daemon is not reachable."
    if [ "$OS" = "macos" ]; then
        echo "Start Docker Desktop, wait until it says Docker is running, then re-run this installer."
    else
        echo "Start Docker and verify your user can access it:"
        echo "  sudo systemctl start docker"
        echo "  docker info"
    fi
    exit 1
}

clone_or_update_repo() {
    if [ -d "$INSTALL_DIR" ]; then
        if [ ! -d "$INSTALL_DIR/.git" ]; then
            log_error "$INSTALL_DIR exists but is not a git checkout."
            log_info "Choose a different directory with --dir PATH."
            exit 1
        fi

        log_info "Existing checkout found; updating $INSTALL_DIR"
        cd "$INSTALL_DIR"
        if [ -n "$(git status --porcelain)" ]; then
            log_warn "Local changes detected. The installer will not overwrite them."
            if prompt_yes_no "Continue without pulling updates?" "yes"; then
                log_info "Keeping local checkout as-is."
                return 0
            fi
            log_info "Stash or commit your changes, then re-run the installer."
            exit 1
        fi
        git fetch origin
        git checkout "$BRANCH"
        git pull --ff-only origin "$BRANCH"
        log_success "Checkout updated"
        return 0
    fi

    mkdir -p "$(dirname "$INSTALL_DIR")"
    log_info "Cloning Team Nexus into $INSTALL_DIR"
    if GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5" git clone --branch "$BRANCH" "$REPO_URL_SSH" "$INSTALL_DIR" 2>/dev/null; then
        log_success "Cloned via SSH"
    else
        rm -rf "$INSTALL_DIR" 2>/dev/null || true
        git clone --branch "$BRANCH" "$REPO_URL_HTTPS" "$INSTALL_DIR"
        log_success "Cloned via HTTPS"
    fi
    cd "$INSTALL_DIR"
}

prepare_env() {
    cd "$INSTALL_DIR"
    if [ ! -f .env ]; then
        cp .env.example .env
        chmod 600 .env 2>/dev/null || true
        log_success "Created .env from .env.example"
    else
        log_info ".env already exists; keeping it"
        chmod 600 .env 2>/dev/null || true
    fi

    echo ""
    echo "Required for live agent runs: at least one model provider key, usually OPENROUTER_API_KEY."
    echo "Required for Atlas Discord gateway: DISCORD_BOT_TOKEN, DISCORD_ALLOWED_USERS, DISCORD_HOME_CHANNEL."
    echo "The installer will not print or collect your secrets. Edit $INSTALL_DIR/.env directly."

    if [ "$EDIT_ENV" = true ] && has_tty; then
        if prompt_yes_no "Open .env in your editor now?" "yes"; then
            if open_editor "$INSTALL_DIR/.env"; then
                log_success ".env editor closed"
            else
                log_warn "No usable editor found. Edit manually: $INSTALL_DIR/.env"
            fi
        fi
    else
        log_info "Edit when ready: $INSTALL_DIR/.env"
    fi
}

nonempty_env_value() {
    local key="$1"
    local value
    value="$(grep -E "^[[:space:]]*${key}=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"
    [ -n "$value" ]
}

check_env_guidance() {
    cd "$INSTALL_DIR"
    local has_provider=false
    local has_discord=true

    for key in OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY GOOGLE_API_KEY; do
        if nonempty_env_value "$key"; then
            has_provider=true
            break
        fi
    done

    for key in DISCORD_BOT_TOKEN DISCORD_ALLOWED_USERS DISCORD_HOME_CHANNEL; do
        if ! nonempty_env_value "$key"; then
            has_discord=false
        fi
    done

    if [ "$has_provider" = true ]; then
        log_success "At least one model provider key appears to be set"
    else
        log_warn "No model provider key appears to be set yet. Live Hermes agent runs will fail until one is added."
    fi

    if [ "$has_discord" = true ]; then
        log_success "Atlas Discord gateway settings appear to be set"
    else
        log_warn "Atlas Discord settings are incomplete. Docker can still build, but gateway use needs DISCORD_BOT_TOKEN, DISCORD_ALLOWED_USERS, and DISCORD_HOME_CHANNEL."
        if [ "$RUN_UP" = true ] && ! prompt_yes_no "Start services anyway?" "no"; then
            RUN_UP=false
            log_info "Will skip make up. Run it later after editing .env."
        fi
    fi
}

run_make_target() {
    local target="$1"
    log_info "Running: make PYTHON=$PYTHON_CMD $target"
    make PYTHON="$PYTHON_CMD" "$target"
}

render_profiles() {
    cd "$INSTALL_DIR"
    run_make_target profile-render
}

run_preflight() {
    cd "$INSTALL_DIR"
    if [ "$RUN_PREFLIGHT" = true ]; then
        run_make_target preflight
    else
        log_info "Skipping make preflight (--skip-preflight)"
    fi
}

build_runtime() {
    cd "$INSTALL_DIR"
    if [ "$RUN_BUILD" = true ]; then
        run_make_target build
    else
        log_info "Skipping make build (--skip-build)"
    fi
}

start_runtime() {
    cd "$INSTALL_DIR"
    if [ "$RUN_UP" = true ]; then
        run_make_target up
    else
        log_info "Skipping make up (--skip-up or incomplete .env)"
    fi
}

print_success() {
    cd "$INSTALL_DIR"
    local dashboard_port
    dashboard_port="$(grep -E '^TEAM_NEXUS_DASHBOARD_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"
    dashboard_port="${dashboard_port:-8180}"

    echo ""
    echo -e "${GREEN}${BOLD}Team Nexus setup guide complete.${NC}"
    echo ""
    echo "Checkout:  $INSTALL_DIR"
    echo "Secrets:   $INSTALL_DIR/.env"
    echo "Runtime:   $INSTALL_DIR/runtime/hermes"
    echo "Profiles:  $INSTALL_DIR/runtime/hermes/profiles"
    echo "Dashboard: http://127.0.0.1:$dashboard_port"
    echo ""
    echo "Next useful commands:"
    echo "  cd $INSTALL_DIR"
    echo "  make ps"
    echo "  make logs SERVICE=atlas-gateway"
    echo "  make doctor PROFILE=atlas"
    echo "  make doctor-all"
    echo "  make kanban-list"
    echo "  make shell PROFILE=forge"
    echo "  make down"
    echo ""
    if [ "$RUN_UP" = false ]; then
        echo "When .env is ready, start Team Nexus with:"
        echo "  cd $INSTALL_DIR && make build && make up"
        echo ""
    fi
    echo "Read next: $INSTALL_DIR/GETTING_STARTED.md"
}

main() {
    print_banner
    print_plan

    print_step "1/9" "Check host prerequisites"
    check_os
    require_prerequisites
    check_docker_running

    print_step "2/9" "Clone or update Team Nexus"
    clone_or_update_repo

    bootstrap_python_deps

    print_step "3/9" "Prepare .env secrets file"
    prepare_env
    check_env_guidance

    print_step "4/9" "Render Hermes profile homes"
    render_profiles

    print_step "5/9" "Run preflight validation"
    run_preflight

    print_step "6/9" "Build shared Docker image"
    build_runtime

    print_step "7/9" "Start runtime services"
    start_runtime

    print_step "8/9" "Show service status"
    if [ "$RUN_UP" = true ]; then
        make ps || true
    else
        log_info "Services were not started."
    fi

    print_step "9/9" "Print next steps"
    print_success
}

main "$@"
