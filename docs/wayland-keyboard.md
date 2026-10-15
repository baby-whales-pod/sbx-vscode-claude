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
 Mac (host)                                         Sandbox (Linux microVM)
┌───────────────────────────────┐                ┌─────────────────────────────────────┐
│ sailor (crates/compositor)    │◄──── vsock ────┤ compositor-guest (crates/compositor- │
│ winit · one native macOS      │  raw scancodes  │ guest, smithay) — the real Wayland   │
│ window per Wayland surface    │                 │ server, creates /run/display/wayland-0│
└───────────────────────────────┘                │        ▲ Wayland client              │
                                                  │   VS Code (the kit's entrypoint)      │
                                                  └─────────────────────────────────────┘
```

1. `sbx run --display` asks for a display for the sandbox. sandboxd sets the `com.docker.sandbox.display=wayland` label on the container.
2. The sandbox engine (docker-next, v0.6.0 or later) reads that label and starts, inside the microVM, sailor's guest compositor (`compositor-guest`), which creates the **`/run/display/wayland-0`** socket.
3. Keyboard/mouse events are captured on the Mac side by `sailor` (the host process, `crates/compositor`, built on winit) and relayed **raw** over **vsock** (the VM-to-host channel) to `compositor-guest`, which opens a native macOS window in return for each Wayland window it shows.
4. VS Code, started with `--ozone-platform=wayland` and software rendering (the VM has no GPU), connects directly to `compositor-guest` — **not** to a passive relay. Its window shows up on your desktop like any app.

## Why the keyboard is in QWERTY

*Updated from the source of [`docker/sailor`](https://github.com/docker/sailor) (Docker's internal repo) — the following is no longer an outside-in guess, it's verified in the code.*

There are actually **two compositors**, not one:

- on the Mac side, `crates/compositor` (built on **winit**) opens one native window per surface and relays **raw** keyboard events (evdev scancodes, not characters) to the microVM over **vsock**;
- inside the microVM, `crates/compositor-guest` (built on **smithay**) is the **real Wayland server**: it creates `/run/display/wayland-0`, owns `wl_seat`/`wl_keyboard`, and VS Code connects to it directly.

![Why the keyboard layout is hardcoded](diagrams/keyboard-path.png)

The keyboard layout is a **constant** in that second compositor, not a missing setting: in `crates/compositor-guest/src/state.rs`, the keyboard is initialized with `XkbConfig { layout: "us", .. }`, and the keymap actually used is a **precompiled US string embedded in the binary** (`xkb_bootstrap/us_keymap.xkb`). That's a deliberate workaround for a crash: compiling a keymap from RMLVO names (`xkb_keymap_new_from_names`) needs an on-disk XKB dataset, which minimal guest images don't ship, and that made `libxkbcommon` **segfault** ([`docker/sailor#1677`](https://github.com/docker/sailor/issues/1677), fixed by embedding the US keymap instead). VS Code can't do anything about it: it gets whatever keymap `compositor-guest` sends, and that's always `us`.

Worth noting: the plumbing for a per-layout setting partly exists already. `compositor-guest` already retranslates some keys case by case — `keymap.rs` turns ⌘ (Super) into Ctrl or Ctrl+Shift depending on the focused app (terminal or not), toggled with `sailor run --no-key-remap` (which passes `display.keymap=0` to the microVM's kernel, read by `container-init`). A future `--keyboard-layout` would likely follow the same path — but as of now, **no issue is open** for it on `docker/sailor`.

## A partial (and costly) fix: a nested compositor, labwc

```
 Mac (host)                         Sandbox
┌───────────────────────┐        ┌────────────────────────────────────────────────┐
│ sailor's compositor   │◄─vsock─┤ compositor-guest (already a real compositor)  │
│  └ "labwc" window     │        │        ▲ client (a single window) ─ us keymap │
└───────────────────────┘        │      labwc  ← fr / mac keymap                  │
                                 │        ▲ labwc's socket ($XDG_RUNTIME_DIR)     │
                                 │      foot, or any other app                    │
                                 └────────────────────────────────────────────────┘
```

**labwc** is a small Wayland compositor built on the wlroots library. `sandbox-desktop` starts it **as a client of `compositor-guest`** — so, with what we now know, as a **third** compositor in the chain (sailor → compositor-guest → labwc → app), not a second one:

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
- **Limitation #1**: VS Code allows a single instance. While the entrypoint's VS Code is running (drawn straight on the display, so in QWERTY), running `sandbox-code` inside `sandbox-desktop` opens the window in the existing instance. For VS Code in AZERTY, the entrypoint itself would have to start VS Code inside labwc.
- **Limitation #2, more serious**: testing that scenario (entrypoint starting inside labwc) made the image noticeably less sharp. The most likely explanation, now that we know labwc nests inside `compositor-guest` (already a full compositor, not a passive relay): a nested wlroots compositor doesn't necessarily negotiate its parent's HiDPI scale factor, and renders at scale 1 while `compositor-guest`/sailor display at Retina scale — hence the blur. Not necessarily unfixable (forcing labwc's output scale), but it only shows up in a real sandbox, and it wasn't adopted as this kit's fix.

**Practical conclusion**: the keyboard layout isn't a setting the kit is missing, nor something a nested compositor can cleanly fix on the image side — it's a constant in sailor's guest compositor (`layout: "us"`, hardcoded). The right fix belongs upstream, in `docker/sailor`, following the same plumbing already used for the ⌘→Ctrl remap (a `--keyboard-layout` flag, a handful of precompiled embedded keymaps like `us_keymap.xkb`). No issue is open on this yet.
