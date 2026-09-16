# Build DeskBound.gb and run the web player against it
default: rom web

# Compile DeskBound.gb in Docker (see tools/build-rom.sh)
rom:
    ./tools/build-rom.sh

# Install web/ dependencies if needed and start the Vite dev server
web:
    cd web && ( [ -d node_modules ] || npm install ) && npm run dev

# Remove the cached gb-studio-cli Docker image, forcing a full rebuild next time
clean-cli:
    docker image rm deskbound-gb-studio-cli:4.3.2
