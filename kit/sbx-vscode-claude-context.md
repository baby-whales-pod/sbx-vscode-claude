VS Code is this sandbox's entrypoint. It runs on the Wayland display named by
`$SANDBOX_WAYLAND_SOCKET` (default `/run/display/wayland-0`) and shows up as a window on the
host. The sandbox session ends when the VS Code window is closed.

Claude Code is installed both as a CLI (`claude`, on PATH) and as the `anthropic.claude-code`
VS Code extension. Use the VS Code integrated terminal or `sbx exec` to run `claude`.

The sandbox has no GPU, so open another VS Code window with `sandbox-code <path>`, which adds the
software-rendering flags; running `/usr/bin/code` without them shows a blank window.

There is no keyring or D-Bus session: VS Code stores secrets with `--password-store=basic`.
Network access is limited by the sandbox policy; the VS Code marketplace is not allowed at runtime,
extensions are baked into the image at build time.
