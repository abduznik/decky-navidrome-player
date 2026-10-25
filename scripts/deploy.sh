#!/usr/bin/env bash
# Install a packaged plugin into a local Decky Loader installation.
# Usage: ./scripts/deploy.sh [path-to-zip]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS_DIR="${DECKY_PLUGINS_DIR:-$HOME/homebrew/plugins}"

if [[ $# -ge 1 ]]; then
    ZIP="$1"
else
    VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$ROOT/package.json")"
    case "$(uname -m)" in
        aarch64|arm64) ARCH="arm64" ;;
        *) ARCH="x86_64" ;;
    esac
    ZIP="$ROOT/out/navidrome-player-${VERSION}-${ARCH}.zip"
fi

if [[ ! -f "$ZIP" ]]; then
    echo "Package not found: $ZIP" >&2
    echo "Run ./scripts/package.sh <arch> after 'pnpm build'." >&2
    exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
python3 -m zipfile -e "$ZIP" "$TMP"

if [[ ! -d "$TMP/navidrome-player" ]]; then
    echo "Unexpected package layout: missing navidrome-player/ folder." >&2
    exit 1
fi

mkdir -p "$PLUGINS_DIR"
rm -rf "$PLUGINS_DIR/navidrome-player"
cp -R "$TMP/navidrome-player" "$PLUGINS_DIR/navidrome-player"

echo "Installed to $PLUGINS_DIR/navidrome-player"
echo "Restart Decky Loader (or Steam) to load the plugin."
