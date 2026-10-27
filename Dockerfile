# Gambar pengembangan gp2midi.
# Engine tetap nol dependensi (Keputusan 1): libfluidsynth di sini hanya untuk
# pyfluidsynth di subpaket gp2midi/play/ — test offline playback, dan playback
# realtime via socket PulseAudio host (Linux; lihat docker-compose.yml).
# Bukannya pengganti spike F2.5 bundling macOS: itu masalah PyInstaller (R3).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libfluidsynth3 \
        timgm6mb-soundfont \
    && rm -rf /var/lib/apt/lists/*

ENV HOME=/tmp \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /work

# Sumber saja, corpus media/ sengaja tidak ikut (bukan bagian dari test suite)
COPY pyproject.toml ./
COPY gp2midi ./gp2midi
COPY tests ./tests
COPY tools ./tools

# venv playback milik kontainer, DI LUAR titik bind mount supaya tidak
# bercampur dengan .venv-app host (biner host tidak valid di dalam kontainer)
RUN python3 -m venv /opt/venv-app \
    && /opt/venv-app/bin/pip install --quiet "pyfluidsynth==1.4.0" numpy

# titik pemasangan volume bernama; kepemilikan ini diwarisi volume pada
# pemasangan pertama, supaya user 1000 bisa membuat venv di dalamnya
RUN mkdir /work/.venv-oracle && chown 1000:1000 /work/.venv-oracle
