#!/usr/bin/env bash
# Compiles DeskBound.gb in a throwaway Ubuntu container that builds
# gb-studio-cli from source, the same way .github/workflows/build-rom.yml does
# in CI. Doing this in Docker sidesteps host-specific packaging quirks (no
# system unzip, non-FHS binaries, etc.) that a native build hits on NixOS.
set -euo pipefail

GB_STUDIO_VERSION="4.3.2"
IMAGE="deskbound-gb-studio-cli:${GB_STUDIO_VERSION}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROM_DIR="$ROOT_DIR/build/rom"

mkdir -p "$ROM_DIR"

echo "==> Building gb-studio-cli image (cached; only reruns when tools/Dockerfile.gb-studio-cli or GB_STUDIO_VERSION changes)"
docker build \
  --build-arg "GB_STUDIO_VERSION=$GB_STUDIO_VERSION" \
  -t "$IMAGE" \
  -f "$ROOT_DIR/tools/Dockerfile.gb-studio-cli" \
  "$ROOT_DIR/tools"

echo "==> Compiling DeskBound.gb"
docker run --rm \
  -v "$ROOT_DIR:/workspace/game:ro" \
  -v "$ROM_DIR:/workspace/rom" \
  "$IMAGE" \
  make:rom /workspace/game/DeskBound.gbsproj /workspace/rom/DeskBound.gb 2>&1 | tee "$ROM_DIR/build.log"

# The compiler skips events it has no handler for, still exits 0, and emits a
# ROM whose scripts are simply missing. Treat that as a failure, same as CI.
if grep -q "No compiler for command" "$ROM_DIR/build.log"; then
  echo "error: GB Studio skipped events while compiling — the ROM would be incomplete." >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/web/public"
cp "$ROM_DIR/DeskBound.gb" "$ROOT_DIR/web/public/DeskBound.gb"

echo "==> ROM built: $ROM_DIR/DeskBound.gb (copied to web/public/DeskBound.gb)"
