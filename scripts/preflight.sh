#!/usr/bin/env bash
set -euo pipefail

make generate
make validate
make compose-config
make check-generated
