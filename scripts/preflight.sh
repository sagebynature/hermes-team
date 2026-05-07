#!/usr/bin/env bash
set -euo pipefail

make validate
make profile-render-dry-run
make profile-render-docker-dry-run
make compose-config
make profile-render
make profile-permissions-check
