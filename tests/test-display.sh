#!/bin/bash
# Smoke test of the kit image WITHOUT sbx: a headless sway compositor stands in
# for the Wayland socket that `sbx run --display` provides, and grim takes a
# screenshot of what VS Code draws on it.
#
# Usage: ./tests/test-display.sh            (from the sbx-vscode-claude folder)
# Output: tests/out/screenshot.png
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE=sbx-vscode-claude:dev
OUT=tests/out
mkdir -p "$OUT/workspace"
echo 'console.log("hello from sbx-vscode-claude")' > "$OUT/workspace/hello.js"
chmod -R a+rwX "$OUT/workspace"

cleanup() { docker rm -f msi-wl msi-ide >/dev/null 2>&1 || true; docker volume rm -f msi-display >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "==> Building the kit image ($IMAGE)"
docker build -q -f kit/kit.dockerfile \
  --build-arg VSCODE_VERSION=latest --build-arg CLAUDE_CODE_VERSION=latest \
  -t "$IMAGE" kit >/dev/null

echo "==> Building and starting the headless Wayland compositor"
docker build -q -t msi-wayland-headless -f tests/wayland-headless.Dockerfile tests >/dev/null
docker volume create msi-display >/dev/null
docker run --rm -u 0 -v msi-display:/run/display ubuntu:26.04 \
  sh -c 'chown 1000:1000 /run/display && chmod 700 /run/display'
docker run -d --name msi-wl -v msi-display:/run/display msi-wayland-headless >/dev/null
for _ in $(seq 1 20); do
  socket=$(docker exec msi-wl sh -c 'ls /run/display | grep -E "^wayland-[0-9]+$" | head -1' || true)
  [ -n "$socket" ] && break
  sleep 1
done
[ -n "$socket" ] || { echo "compositor did not start"; exit 1; }

echo "==> Starting the IDE on /run/display/$socket"
docker run -d --name msi-ide --shm-size=512m \
  -v msi-display:/run/display \
  -v "$PWD/$OUT/workspace:/home/agent/workspace" \
  -e SANDBOX_WAYLAND_SOCKET="/run/display/$socket" \
  "$IMAGE" >/dev/null
sleep 15

echo "==> Windows on the compositor:"
docker exec -e SWAYSOCK="$(docker exec msi-wl sh -c 'ls /run/display/sway-ipc.*.sock')" msi-wl \
  swaymsg -t get_tree | grep -E '"app_id"' || { echo "no window found"; exit 1; }

docker exec -e WAYLAND_DISPLAY="$socket" msi-wl grim /tmp/shot.png
docker cp msi-wl:/tmp/shot.png "$OUT/screenshot.png"
echo "==> Screenshot: $OUT/screenshot.png"
