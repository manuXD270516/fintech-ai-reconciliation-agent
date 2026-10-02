#!/bin/sh
# T01 (Linux): clean clone + locked guide + static gate. No Docker inside on purpose,
# so doctor must report the missing prerequisite (T02) while the static gate passes.
#
# Environment image (node pinned by digest + uv binary from its pinned image):
#   FROM ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 AS uv
#   FROM node:22.23.1-trixie@sha256:3145536027ca5268e24654f7efebf1dbdd684cda3708324e6c53f4ad61af8710
#   COPY --from=uv /uv /uvx /usr/local/bin/
# Run from the repository root:
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/openspec/changes/bootstrap-mvp-foundation/evidence/t01-linux-clean-clone.sh:/t01.sh:ro" m0-t01-linux:local sh /t01.sh
set -u
step() { name="$1"; shift; start=$(date +%s); "$@"; code=$?; echo "### STEP $name exit=$code seconds=$(( $(date +%s) - start ))"; }
git config --global --add safe.directory '*'
step "git clone" git clone --quiet /src /work/repo
cd /work/repo || exit 1
echo "commit: $(git rev-parse --short HEAD)"
echo "platform: $(uname -srm); $(. /etc/os-release; echo "$PRETTY_NAME")"
step "python preinstalled?" sh -c 'command -v python3 || echo "no python3 on PATH"'
step "uv sync --locked" uv sync --locked
step "python version" uv run python -c "import sys, platform; print(sys.version, platform.platform())"
step "npm ci" npm ci --no-audit --no-fund
step "copy env" cp .env.example .env
step "doctor (expected: docker missing)" uv run python scripts/doctor.py
step "gate static" uv run python scripts/gate.py static
