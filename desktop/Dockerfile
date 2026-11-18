# syntax=docker/dockerfile:1
# Anki desktop on a server, used from a browser (desktop/README.md): Anki
# from PyPI, unmodified, in LinuxServer's Selkies desktop, which streams the
# screen and sound to the browser and sends back the keyboard and mouse.
# Everything Anki keeps (profiles, collections, media, add-ons, backups) is
# in /config/Anki2.
FROM ghcr.io/linuxserver/baseimage-selkies:debiantrixie

ARG ANKI_PY_VERSION

LABEL org.opencontainers.image.source="https://github.com/krmanik/kioku" \
      org.opencontainers.image.description="Anki desktop on your server, used from any browser"

ENV HOME=/config \
    TITLE=Anki \
    PIXELFLUX_WAYLAND=true \
    QTWEBENGINE_DISABLE_SANDBOX=1 \
    NO_GAMEPAD=true \
    SELKIES_ENABLE_BINARY_CLIPBOARD=true

RUN \
  test -n "$ANKI_PY_VERSION" && \
  apt-get update && \
  apt-get install -y --no-install-recommends \
    cabextract \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    libasound2t64 \
    libminizip1t64 \
    libnss3 \
    libxcb-cursor0 \
    libxkbcommon-x11-0 \
    libxkbfile1 \
    mpv \
    python3-venv && \
  python3 -m venv /opt/anki && \
  /opt/anki/bin/pip install --no-cache-dir "aqt[qt]==$ANKI_PY_VERSION" && \
  cp /opt/anki/lib/python3*/site-packages/_aqt/data/qt/icons/anki.png \
    /usr/share/selkies/www/icon.png && \
  echo "maximize only the main window ('User 1 - Anki'), not dialogs" && \
  sed -i 's|<windowRule identifier="\*"><action name="Maximize" /></windowRule>|<windowRule title="* - Anki"><action name="Maximize" /></windowRule>|' \
    /defaults/labwc.xml && \
  grep -q 'title="\* - Anki"' /defaults/labwc.xml && \
  apt-get clean && \
  rm -rf \
    /config/.cache \
    /tmp/* \
    /var/lib/apt/lists/* \
    /var/tmp/*

COPY root/ /
RUN chmod 755 /usr/local/bin/anki-session /usr/local/bin/anki-close \
    /usr/local/bin/anki-ms-fonts /usr/local/bin/anki-packages

EXPOSE 3000 3001
VOLUME /config
