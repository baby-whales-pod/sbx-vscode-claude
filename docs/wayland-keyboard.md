# Wayland, the sbx display and the keyboard

*🇫🇷 Version française : [wayland-keyboard.fr.md](wayland-keyboard.fr.md)*

This document explains how a Linux app running in a Docker Sandbox can show a window on your Mac, why the keyboard ends up in QWERTY there, and how `sandbox-desktop` fixes it. It also lists the sbx and Docker features involved.

## Wayland in two minutes

**Wayland** is the display protocol of modern Linux desktops, the successor to X11. It connects two roles:

- **The compositor** (the "server") owns the screen, the keyboard and the mouse. It assembles everyone's windows into one image and decides who receives keystrokes.
- **The clients** are the apps (VS Code, a terminal…). Each one draws its windows' content into memory buffers and hands them to the compositor.

They talk over a **Unix socket**. A client finds its compositor through two environment variables: `XDG_RUNTIME_DIR` (the directory) and `WAYLAND_DISPLAY` (the socket name, e.g. `wayland-0`). An absolute path in `WAYLAND_DISPLAY` works too.

### What about the keyboard?

This is the key point for what follows. The compositor doesn't send letters to apps. It sends:

1. an **XKB keymap**, the table that says "key no. 16 gives `a`" (that's the layout: `fr`, `us`, `ch`…);
2. then, on every keystroke, **the physical number of the key**.

The app turns the number into a character with the keymap it received. **So the keyboard layout is chosen by the compositor, not by the app.**

### A compositor inside a compositor

A compositor can itself be a client of another compositor. That's called a **nested** compositor. It opens a single window on its parent, shows its own clients inside it, and **sends them its own keymap**. That's the whole idea behind the fix described below.

## How a sandbox window reaches your Mac

```
 Mac (host)                               Sandbox (Linux microVM)
┌──────────────────────────────┐        ┌──────────────────────────────────┐
│ sailor's Wayland compositor  │◄─vsock─┤ /run/display/wayland-0           │
│ (one native macOS window     │        │        ▲                         │
│  per Wayland window)         │        │        │ Wayland client          │
└──────────────────────────────┘        │   VS Code (the kit's entrypoint) │
                                        └──────────────────────────────────┘
```

1. `sbx run --display` asks for a display for the sandbox. sandboxd sets the `com.docker.sandbox.display=wayland` label on the container.
2. The sandbox engine (docker-next, v0.6.0 or later) reads that label and creates the **`/run/display/wayland-0`** socket in the microVM.
3. That socket is relayed over **vsock** (the VM-to-host channel) to a Wayland compositor running on the host, provided by **sailor**, the Docker Sandboxes hypervisor. It opens a native macOS window for each Wayland window.
4. VS Code, started with `--ozone-platform=wayland` and software rendering (the VM has no GPU), connects to that socket. Its window shows up on your desktop like any app.

## Why the keyboard is in QWERTY

sailor's compositor is a native library (Rust/winit) with no keyboard-layout setting: neither sbx, docker-next nor the display API expose one. In practice, apps drawn straight on `/run/display/wayland-0` get a keymap that doesn't follow the Mac's layout, and you type in QWERTY. The app can't do anything about it: it uses the keymap the compositor gives it.

## The fix: a nested compositor, labwc

```
 Mac (host)                         Sandbox
┌───────────────────────┐        ┌───────────────────────────────────────────┐
│ sailor's compositor   │◄─vsock─┤ /run/display/wayland-0                    │
│  └ "labwc" window     │        │        ▲ client (a single window)         │
└───────────────────────┘        │      labwc  ← fr / mac keymap             │
                                 │        ▲ labwc's socket ($XDG_RUNTIME_DIR)│
                                 │      foot, or any other app               │
                                 └───────────────────────────────────────────┘
```

**labwc** is a small Wayland compositor built on the wlroots library. `sandbox-desktop` starts it **as a client** of the sandbox display:

- labwc opens **a single window** on the Mac and creates its own socket for the apps it starts;
- it receives keystrokes from sailor and **translates them again with its own keymap**: the one from `XKB_DEFAULT_LAYOUT` / `XKB_DEFAULT_VARIANT`, read from `~/.config/labwc/environment`;
- apps started **inside** labwc (foot, or whatever you pass to `sandbox-desktop`) get that keymap: they type in AZERTY.

What `sandbox-desktop` (in `kit/bin/`) does, in order:

| Step | Why |
|---|---|
| Checks that `/run/display/wayland-0` exists | Without `--display` at creation, there's no display |
| `WAYLAND_DISPLAY=/run/display/wayland-0` (absolute path) | By default sbx sets `WAYLAND_DISPLAY=wayland-0` in `XDG_RUNTIME_DIR=/run/user/1000`. That socket is sbx's **clipboard bridge**, not a compositor: labwc would fail to connect to it |
| `WLR_RENDERER=pixman` | Software rendering: the VM has no GPU |
| `LANG=fr_FR.UTF-8` | Locale generated in the image (`locale-gen`); otherwise foot complains about a `C` locale |
| Writes `~/.config/labwc/environment` from the kit args | The documented way to set labwc's layout, and the one validated by hand in a real sandbox |
| Starts the app with `SANDBOX_WAYLAND_SOCKET` pointing at labwc's socket | `sandbox-code` reads that variable: without it, VS Code would connect to the sandbox display rather than to labwc |

## Features used

### Docker Sandboxes (sbx)

| Feature | Role here |
|---|---|
| **Sandbox = microVM** (docker-next engine, sailor hypervisor) | Isolates the IDE and the agent from the Mac. Each sandbox has its own Linux kernel and its own network |
| **`--display`** (experimental, feature flag `feature.sandbox-display`, enabled with `DOCKER_SANDBOXES_FEATURE_SANDBOX_DISPLAY=1`) | Provides the `/run/display/wayland-0` Wayland socket, relayed over vsock to sailor's compositor on the host. Must be passed **at creation**. Clipboard and drag-and-drop are deliberately disabled on this display |
| **Kits v3** (`kind: workload`, `kit.yaml` + `kit.dockerfile`) | Describe the environment: the image to build, the entrypoint (VS Code), the capabilities |
| **Kit args** (`--kit-arg name=value`) | `vscodeVersion` and `claudeCodeVersion` are **build** args (`buildArg`). `waylandSocket`, `keyboardLayout` and `keyboardVariant` are **runtime** args, passed as environment variables (`env`) |
| **`network-policy` capability** | Lists the only domains reachable while the IDE runs, enforced from outside the VM |
| **`agent-context` capability** | Tells Claude Code about the environment it runs in |
| **`sbx exec -it`** | Starts `sandbox-desktop` in a running sandbox, with a terminal attached |
| **Kit validation** | `kit.yaml` was checked with the official v3 spec validator (`sandbox-kit-spec`), with no errors or warnings |

### Docker

| Feature | Role here |
|---|---|
| **Dockerfile / BuildKit** | `kit.dockerfile` builds the kit image. `RUN --mount=type=bind` makes the kit folder available during the build without copying it into a layer: only the installed launchers stay in the image |
| **Base image** `docker/sandbox-templates:shell` | The official sandbox template (Ubuntu 26.04, `agent` user, basic tools) |
| **Shared Docker volume** (tests) | `tests/test-display.sh` and `tests/test-desktop.sh` share a **headless sway** compositor's socket between two containers, standing in for `/run/display/wayland-0`. That allows testing without `sbx` or a screen |

### On the Linux side, in the image

| Component | Role |
|---|---|
| **labwc** | Nested compositor that applies the keyboard layout |
| **xkbcommon** (`XKB_DEFAULT_LAYOUT`, `XKB_DEFAULT_VARIANT`) | The library that builds the keymap from the layout |
| **foot** | Lightweight Wayland terminal, the app started by default |
| **locales** (`fr_FR.UTF-8`) | The French locale, generated at build |

## What was checked

- **In a real sandbox**, by hand: nested labwc with the `~/.config/labwc/environment` file gives AZERTY.
- **Without sbx**, with a headless compositor: the install step works on Ubuntu 26.04, labwc opens a single window, foot draws inside labwc, and the layout comes from the kit args.
- **Limitation**: VS Code allows a single instance. While the entrypoint's VS Code is running (drawn straight on the display, so in QWERTY), running `sandbox-code` inside `sandbox-desktop` opens the window in the existing instance. For VS Code in AZERTY, the entrypoint itself would have to start VS Code inside labwc.
