# Build DeskBound.gb and run the web player against it
default: rom web

# Compile DeskBound.gb in Docker (see tools/build-rom.sh)
rom:
    ./tools/build-rom.sh

# Needs gb-strudel >= 1.1 (positional output path).
[doc('Compile bgm/*.gbs, or only the given songs, to .uge files in assets/music/')]
[positional-arguments]
music *songs:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v gb-strudel >/dev/null; then
      echo "error: gb-strudel not found on PATH — install it with 'cargo install gb-strudel'" >&2
      echo "       or grab a binary from https://github.com/KeeTraxx/gb-strudel/releases" >&2
      exit 1
    fi
    shopt -s nullglob
    songs=("$@")
    [ ${#songs[@]} -gt 0 ] || songs=(bgm/*.gbs)
    if [ ${#songs[@]} -eq 0 ]; then
      echo "error: no .gbs songs in bgm/" >&2
      exit 1
    fi
    mkdir -p assets/music
    for song in "${songs[@]}"; do
      gb-strudel build "$song" "assets/music/$(basename "$song" .gbs).uge"
    done

# Install web/ dependencies if needed and start the Vite dev server
web:
    cd web && ( [ -d node_modules ] || npm install ) && npm run dev

# Remove the cached gb-studio-cli Docker image, forcing a full rebuild next time
clean-cli:
    docker image rm deskbound-gb-studio-cli:4.3.2
