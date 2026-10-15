#!/bin/bash
# Smoke test of sandbox-desktop WITHOUT sbx: the headless sway compositor stands
# in for the sandbox display, as in test-display.sh. Checks that labwc opens one
# window on it, that the app it starts draws inside labwc rather than straight
# on the display, and that labwc got the keyboard layout from the kit args.
#
# Usage: ./tests/test-desktop.sh            (from the sbx-vscode-claude folder)
# Output: tests/out/desktop-screenshot.png
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE=sbx-vscode-claude:dev
OUT=tests/out
mkdir -p "$OUT"

cleanup() { docker rm -f msi-wl msi-desk >/dev/null 2>&1 || true; docker volume rm -f msi-display >/dev/null 2>&1 || true; }
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

echo "==> Starting sandbox-desktop on /run/display/$socket (layout ch / fr)"
# The entrypoint is replaced so VS Code doesn't start: only labwc + foot run.
docker run -d --name msi-desk --entrypoint sleep \
  -v msi-display:/run/display \
  -e SANDBOX_WAYLAND_SOCKET="/run/display/$socket" \
  -e SANDBOX_KEYBOARD_LAYOUT=ch -e SANDBOX_KEYBOARD_VARIANT=fr \
  "$IMAGE" infinity >/dev/null
docker exec -d msi-desk sh -c 'sandbox-desktop > /tmp/desktop.log 2>&1'
sleep 8

swaymsg() {
  docker exec -e SWAYSOCK="$(docker exec msi-wl sh -c 'ls /run/display/sway-ipc.*.sock')" msi-wl swaymsg "$@"
}

echo "==> Windows on the outer compositor (expect labwc only, not foot):"
tree=$(swaymsg -t get_tree)
echo "$tree" | grep -E '"app_id"' || true
echo "$tree" | grep -q '"app_id": "foot"' && { echo "FAIL: foot drew straight on the display"; exit 1; }
echo "$tree" | grep -qE '"app_id": "(labwc|wlroots)' || { echo "FAIL: no labwc window"; docker exec msi-desk cat /tmp/desktop.log; exit 1; }

echo "==> foot running inside labwc:"
docker exec msi-desk pgrep -a foot || { echo "FAIL: foot not running"; docker exec msi-desk cat /tmp/desktop.log; exit 1; }

echo "==> labwc environment file:"
env_file=$(docker exec msi-desk cat /home/agent/.config/labwc/environment)
echo "$env_file"
grep -q '^XKB_DEFAULT_LAYOUT=ch$' <<<"$env_file" && grep -q '^XKB_DEFAULT_VARIANT=fr$' <<<"$env_file" \
  || { echo "FAIL: layout not taken from the kit args"; exit 1; }

docker exec -e WAYLAND_DISPLAY="$socket" msi-wl grim /tmp/shot.png
docker cp msi-wl:/tmp/shot.png "$OUT/desktop-screenshot.png"
echo "==> OK. Screenshot: $OUT/desktop-screenshot.png"
