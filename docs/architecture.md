# My Secure IDE — Architecture

*🇫🇷 Version française : [architecture.fr.md](architecture.fr.md)*

## Overview

![Runtime architecture](diagrams/runtime-architecture.svg)

My Secure IDE is a **workload kit** (Kits v3) for Docker Sandboxes. Unlike a classic kit, where the agent runs in a terminal, here **VS Code is the sandbox's entrypoint**. It draws its window on a Wayland display that `sbx` provides, and that window shows up on the host desktop.

| Component | Where it runs | Role |
|---|---|---|
| **Host desktop** | Host | Shows the VS Code window (native compositor). Gets **only the pixels and input events**: no files, no processes. |
| **VS Code (Electron)** | Sandbox | Entrypoint. Wayland client in software rendering (no GPU). Opens the mounted workspace. |
| **Claude Code** | Sandbox | Coding agent: VS Code extension `anthropic.claude-code` + `claude` CLI. |
| **Workspace** | Mounted into the sandbox | The only host folder the IDE and the agent can see and change. |
| **sbx network policy** | sbx proxy | Filters all outbound traffic. Only the kit's allowlist (Anthropic) gets through, on top of the organization's policies. |

## Lifecycle

![From kit sources to a running IDE](diagrams/kit-build-and-run.svg)

1. **Kit sources**: `kit.yaml` (descriptor) + `kit.dockerfile` (image) + the `bin/`, `config/` and `applications/` files.
2. **Build**: `sbx` builds the image from `docker/sandbox-templates:shell` and embeds the kit descriptor (args, capabilities, policy) in the image annotations.
3. **Run**: `sbx run --display ./kit <workspace>` creates the microVM, mounts the workspace, applies the network policy and provides the Wayland socket.
4. **Share** (optional): `sbx kit push` publishes the kit to an OCI registry. Everyone else runs `sbx run --display <ref>`.

## Startup sequence

```
sbx run --display ./kit ~/projects/my-app
  │
  ├─ sbx: creates the microVM, mounts ~/projects/my-app, applies network-policy@1,
  │       provides /run/display/wayland-0 (Wayland socket wired to the host compositor)
  │
  └─ entrypoint: tini -- /opt/sbx-vscode-claude/bin/sbx-vscode-claude-session
        ├─ waits for the Wayland socket (up to 120 s, then a clear error: "--display?")
        └─ exec sandbox-code --wait "$PWD"
              └─ /usr/bin/code --ozone-platform=wayland --disable-gpu --no-sandbox
                                --password-store=basic …
                    └─ VS Code window → host compositor
```

- **`tini`** reaps Electron's child processes (renderer, extension host…).
- **`--wait`** keeps the VS Code process in the foreground: closing the window ends the session.
- **`sbx exec`** still gives a shell, e.g. to run `claude` without going through the window.

## Kit v3 descriptor (`kit.yaml`)

| Section | Content |
|---|---|
| `kind: workload` | Complete kit: it provides the image **and** the entrypoint (as opposed to a `mixin`, which extends an existing kit). |
| `args` | `vscodeVersion`, `claudeCodeVersion` (build args), `waylandSocket` (runtime env `SANDBOX_WAYLAND_SOCKET`). |
| `com.docker.sandbox/sbx@1` | Standard sandbox integration (shell template, `sbx exec`…). |
| `com.docker.sandbox/network-policy@1` | Runtime allowlist: `api.anthropic.com`, `*.anthropic.com`, `claude.ai`, `*.claude.ai`, `claude.com`, `*.claude.com`. |
| `com.docker.sandbox/agent-context@1` | `sbx-vscode-claude-context.md`: tells the agent how the environment works (Wayland display, no GPU, marketplace blocked…). |

## Design choices

| Choice | Why |
|---|---|
| **VS Code as the entrypoint** (not a full desktop) | The host sees **one application window**, not a remote desktop. Lighter, and more natural for the developer. |
| **Wayland + software rendering** | `sbx --display` provides a Wayland socket. The sandbox has no GPU, so `--disable-gpu` keeps the window from staying blank. |
| **Extensions and CLI baked in at build time** | No dependency on the marketplace at runtime, which shrinks the allowlist. Identical, versioned environment for everyone (`--kit-arg`). |
| **Default VS Code settings** | No telemetry, no automatic updates, Copilot onboarding disabled (`chat.disableAIFeatures`). The demo goes straight to Claude Code. |
| **`--password-store=basic`** | No keyring or D-Bus in the sandbox. Without it, VS Code fails when storing secrets. |
| **Claude Code installed outside `$HOME` (npm prefix)** | A mount cannot hide it. The unneeded musl binaries are removed to save ≈ 250 MB. |

## Security model

- **Files**: only the workspace is mounted. The rest of the host (`~/.ssh`, `~/.aws`, other projects) is out of reach for the IDE **and** the agent.
- **Network**: all outbound traffic goes through the sbx proxy. The kit allows only what Claude Code needs, and the organization's policies (AI Gov) apply on top.
- **Display**: the host compositor receives the window's rendering and sends back keyboard and mouse input. That is the only channel between the IDE and the host desktop.
- **Reproducibility / trust**: the kit can be signed (`sbx kit sign`) and verified (`sbx kit verify`) before it is distributed.

## Testing without sbx

`tests/test-display.sh` reproduces the `--display` contract without `sbx`. A **headless sway** compositor (pixman rendering) shares its Wayland socket with the kit container through a Docker volume, playing the role of `/run/display/wayland-0`. The script checks that a `com.microsoft.VSCode` window appears and takes a screenshot with `grim`.

What this test **does not** cover: the microVM, the network policy, the workspace mount by `sbx`, and the host compositor's rendering.

## Diagrams

The `.drawio` (editable in app.diagrams.net), `.svg` and `.png` files in `diagrams/` are produced by `diagrams/generate.py`. One description per diagram drives both formats. To edit a diagram:

```bash
cd docs/diagrams
python3 generate.py                          # regenerates .drawio + .svg
for f in runtime-architecture kit-build-and-run; do rsvg-convert -o $f.png $f.svg; done
```
