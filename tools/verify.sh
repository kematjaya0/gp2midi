#!/usr/bin/env bash
# Tiga tingkat verifikasi. Jalankan ini sebelum menyatakan sebuah fase selesai.
set -uo pipefail

cd "$(dirname "$0")/.."
status=0
run() { echo; echo "== $1"; shift; "$@" || status=1; }

run "1/4 unit test" python3 -m unittest discover -s tests -t .

echo; echo "== 2/4 invarian korpus (durasi beat harus mengisi tiap bar)"
shopt -s nullglob
corpus=(media/*.gp media/*.gp5)
if [ ${#corpus[@]} -eq 0 ]; then
    echo "  tidak ada file di media/ — dilewati"
else
    for file in "${corpus[@]}"; do
        python3 -m gp2midi check "$file" || status=1
    done
fi

echo; echo "== 3/4 oracle (baca hasil pakai mido, parser independen)"
venv=.venv-oracle
if [ ! -x "$venv/bin/python" ]; then
    echo "  menyiapkan $venv (sekali saja; python3-venv Ubuntu melarang pip ke sistem)"
    python3 -m venv "$venv" >/dev/null 2>&1 || { echo "  GAGAL buat venv"; exit 1; }
    "$venv/bin/pip" install --quiet mido >/dev/null 2>&1 || { echo "  GAGAL pasang mido"; exit 1; }
fi
if [ ${#corpus[@]} -gt 0 ]; then
    out=$(mktemp -d)
    for file in "${corpus[@]}"; do
        python3 -m gp2midi convert "$file" -o "$out/$(basename "$file").mid" >/dev/null || status=1
        python3 -m gp2midi convert "$file" --merge -o "$out/$(basename "$file").merged.mid" >/dev/null || status=1
    done
    "$venv/bin/python" tools/verify_midi.py "$out"/*.mid || status=1
    "$venv/bin/python" tools/verify_tempo.py "$out" || status=1
    rm -rf "$out"
fi

echo; echo "== 4/4 playback (senyap; ukur drift terhadap jam dinding)"
app=.venv-app
if [ ! -x "$app/bin/python" ]; then
    echo "  $app belum ada — dilewati. Buat dengan: python3 -m venv $app && $app/bin/pip install 'pyfluidsynth==1.4.0' numpy"
else
    "$app/bin/python" -m unittest discover -s tests -t . || status=1
    song="media/seventeen-Menemukanmu-05-16-2026.gp"
    if [ -f "$song" ]; then
        if [ "${VERIFY_PLAYBACK:-0}" = "1" ]; then
            echo "  lagu penuh (~255 detik), VERIFY_PLAYBACK=1"
            "$app/bin/python" -m gp2midi play "$song" --silent --report || status=1
        else
            echo "  cuplikan 20 detik; set VERIFY_PLAYBACK=1 untuk lagu penuh"
            "$app/bin/python" -m gp2midi play "$song" --silent --seconds 20 --report || status=1
        fi
    fi
fi

echo
[ $status -eq 0 ] && echo "SEMUA LOLOS" || echo "ADA YANG GAGAL"
exit $status
