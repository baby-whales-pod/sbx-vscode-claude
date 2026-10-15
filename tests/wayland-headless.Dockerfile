FROM ubuntu:26.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends sway grim && rm -rf /var/lib/apt/lists/*
RUN userdel ubuntu 2>/dev/null; useradd -u 1000 -m agent
USER agent
ENV WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman XDG_RUNTIME_DIR=/run/display
CMD ["sway","-c","/dev/null"]
