#!/usr/bin/env bash
# Build a Decky-installable zip for an architecture.
# The plugin is pure Python + JavaScript, so both zips contain identical code;
# the architecture suffix exists so arm64 users have a clearly named artifact.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:-$(uname -m)}"

case "$ARCH" in
    x86_64|amd64)
        ARCH="x86_64"
        ;;
    aarch64|arm64)
        ARCH="arm64"
        ;;
    *)
        echo "Unsupported architecture: $ARCH (expected x86_64 or arm64)" >&2
        exit 1
        ;;
esac

VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$ROOT/package.json")"
STAGE="$ROOT/out/navidrome-player"
OUTPUT="$ROOT/out/navidrome-player-${VERSION}-${ARCH}.zip"

if [[ ! -f "$ROOT/dist/index.js" ]]; then
    echo "dist/index.js is missing. Run 'pnpm build' first." >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"

cp "$ROOT/plugin.json" "$ROOT/package.json" "$ROOT/main.py" "$ROOT/decky.pyi" "$ROOT/README.md" "$ROOT/LICENSE" "$STAGE/"
cp -R "$ROOT/dist" "$STAGE/dist"
cp -R "$ROOT/py_modules" "$STAGE/py_modules"
cp -R "$ROOT/assets" "$STAGE/assets"

find "$STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$STAGE" -type f -name '*.pyc' -delete

rm -f "$OUTPUT"
python3 - "$ROOT/out" "$STAGE" "$OUTPUT" <<'PY'
import os
import shutil
import sys

out_dir, stage, output = sys.argv[1], sys.argv[2], sys.argv[3]
base = output[:-4]
shutil.make_archive(base, "zip", root_dir=out_dir, base_dir=os.path.basename(stage))
print(f"Created {output}")
PY

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$OUTPUT" | tee "$OUTPUT.sha256"
fi
