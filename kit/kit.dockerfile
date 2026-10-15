# syntax=docker/dockerfile:1
# My Secure IDE: VS Code on the sandbox's Wayland display, with Claude Code
# (CLI + VS Code extension) preinstalled. Built on the shell template; VS Code
# replaces the template's bash as the entrypoint, and tini stays in front of it
# to reap Electron's child processes.
FROM docker/sandbox-templates:shell

ARG VSCODE_VERSION
ARG CLAUDE_CODE_VERSION

USER root

# VS Code from Microsoft's apt repository, plus the libraries Electron needs to
# draw on Wayland without a GPU (software rendering through Mesa).
RUN set -eux; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg; \
    chmod a+r /etc/apt/keyrings/microsoft.gpg; \
    echo "deb [arch=amd64,arm64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/code stable main" \
      > /etc/apt/sources.list.d/vscode.list; \
    apt-get update; \
    if [ "${VSCODE_VERSION}" = "latest" ]; then pkg=code; \
    else pkg="code=$(apt-cache madison code | awk -v v="${VSCODE_VERSION}" '$3 ~ "^"v"-" {print $3; exit}')"; fi; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      "$pkg" \
      libgl1-mesa-dri libegl1 libgbm1 libwayland-client0 libwayland-egl1 libwayland-cursor0 \
      libxkbcommon0 libdecor-0-0 libdecor-0-plugin-1-gtk libgtk-3-0t64 libnss3 libasound2t64 \
      libsecret-1-0 xdg-utils fonts-dejavu-core adwaita-icon-theme; \
    rm -rf /var/lib/apt/lists/*; \
    # The pin is a claim about content: make the build enforce it.
    if [ "${VSCODE_VERSION}" != "latest" ]; then \
      test "$(dpkg-query -W -f='${Version}' code | cut -d- -f1)" = "${VSCODE_VERSION}"; \
    fi; \
    ! ldd /usr/share/code/code | grep -q "not found"

# labwc + foot for sandbox-desktop: a nested desktop that applies its own
# keyboard layout, since windows drawn straight on the sandbox display don't
# follow the host's. With recommends, as tested by hand in a running sandbox.
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y labwc foot locales; \
    rm -rf /var/lib/apt/lists/*; \
    locale-gen fr_FR.UTF-8

# Launchers, the session entrypoint and the default VS Code settings. `install`
# rather than COPY --chmod: on a directory copy, --chmod also strips the execute
# bit from the directories, which leaves them unreadable to the agent.
RUN --mount=type=bind,target=/tmp/kit set -eux; \
    install -D -m 0755 -t /opt/sbx-vscode-claude/bin /tmp/kit/bin/*; \
    install -D -m 0644 -t /opt/sbx-vscode-claude/config /tmp/kit/config/*; \
    install -D -m 0644 -t /usr/local/share/applications /tmp/kit/applications/*.desktop

USER agent

# Claude Code CLI, installed into the template's npm prefix (outside the
# workspace, so a mount cannot hide it).
RUN set -eux; \
    if [ "${CLAUDE_CODE_VERSION}" = "latest" ]; then spec=@anthropic-ai/claude-code; \
    else spec="@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"; fi; \
    npm install -g "$spec"; \
    npm cache clean --force; \
    # npm pulls both the glibc and the musl native builds; Ubuntu only needs glibc.
    rm -rf "${NPM_CONFIG_PREFIX}"/lib/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-linux-*-musl; \
    claude --version

# The Claude Code VS Code extension and the default user settings are baked at
# build time, so the running IDE never needs to reach the marketplace.
RUN set -eux; \
    mkdir -p /home/agent/.config/Code/User; \
    install -m 0644 /opt/sbx-vscode-claude/config/settings.json /home/agent/.config/Code/User/settings.json; \
    install -m 0644 /opt/sbx-vscode-claude/config/argv.json /home/agent/.vscode-argv.json; \
    mkdir -p /home/agent/.vscode; \
    mv /home/agent/.vscode-argv.json /home/agent/.vscode/argv.json; \
    code --install-extension anthropic.claude-code --force; \
    code --list-extensions | grep -qi '^anthropic.claude-code$'

# /opt/sbx-vscode-claude/bin comes first so its launchers win.
ENV PATH=/opt/sbx-vscode-claude/bin:${PATH}

WORKDIR /home/agent/workspace

# Setting ENTRYPOINT drops the template's CMD ["bash"]; the empty CMD says so.
ENTRYPOINT ["tini", "--", "/opt/sbx-vscode-claude/bin/sbx-vscode-claude-session"]
CMD []
