#!/usr/bin/env bash
# One-shot local development install: build, package for this machine, deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
python3 -m unittest discover -s tests -v

case "$(uname -m)" in
    aarch64|arm64) ARCH="arm64" ;;
    *) ARCH="x86_64" ;;
esac

./scripts/package.sh "$ARCH"
VERSION="$(python3 -c 'import json; print(json.load(open("package.json"))["version"])')"
./scripts/deploy.sh "out/navidrome-player-${VERSION}-${ARCH}.zip"
