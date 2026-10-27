# PRD — Guitar Pro / MIDI Player & Mixer

Status: draft · 2026-10-27 · target platform: Linux x86_64, macOS Intel (x86_64)

## 1. Masalah

Membuka file Guitar Pro untuk latihan butuh Guitar Pro itu sendiri (berbayar, tidak jalan di Linux). Yang dibutuhkan untuk latihan sebetulnya sempit: dengar tiap track terpisah, matikan track yang sedang dilatih, perlambat tempo, geser nada ke kunci yang nyaman, dan metronom. Tidak butuh editor notasi.

## 2. Lingkup

Aplikasi desktop yang membuka `.gp`, `.gp5`, dan `.mid`, menampilkan track sebagai mixer + piano roll, memainkannya dengan soundfont, dan mengekspor hasilnya ke MIDI atau MP3.

**Non-goal (eksplisit, supaya tidak merembet):**

- Mengedit atau menulis not. Aplikasi ini read-only terhadap musiknya.
- Render notasi balok / tablatur. Keputusan sadar: itu jalur alphaTab dan arsitektur yang berbeda.
- Artikulasi yang perlu event kontinu: bend, slide, vibrato, trill, tremolo picking. Diparsir tapi tidak dibunyikan.
- Mixing: EQ, reverb, kompresi. Hanya volume dan pan.
- Tulis balik ke format Guitar Pro.

## 3. Pengguna & kriteria sukses

Satu persona: pemain gitar yang latihan dari file tab.

Aplikasi dianggap berhasil kalau: buka file → solo track gitar → turunkan tempo ke 70% → transpose -2 → nyalakan metronom, semuanya tanpa membuka manual dan tanpa jeda yang terasa. Lalu ekspor MP3 untuk dilatih di HP.

## 4. Stack

| Lapis | Pilihan | Pin / catatan |
|---|---|---|
| GUI | PySide6 | `6.9.*` — seri terakhir yang build untuk macOS 12; 6.12 naik ke macOS 14+ |
| Piano roll | QGraphicsView | culling + zoom bawaan |
| Audio | FluidSynth 2.x + pyfluidsynth | ctypes, `find_library` → lihat Risiko R1 |
| Scheduler | `fluidsynth.Sequencer` | timing di C, bebas jitter GIL |
| `.gp` / `.gpif` | engine `gp2midi` (sudah ada) | — |
| `.gp5` / `.gp4` / `.gp3` | PyGuitarPro `0.9.*` | pitch harus dihitung sendiri, lihat F8 |
| `.mid` | mido | pure Python, aman dibundel |
| MP3 | lameenc | wheel `macosx_10_9_x86_64` + manylinux |
| Soundfont | TimGM6mb.sf2 (~6 MB) | bisa diganti user ke SF2 lain |
| Bundle | PyInstaller | AppImage (Linux), .app → .dmg (macOS) |

## 5. Keputusan arsitektur

**K1 — Scheduler sendiri, bukan MIDI player bawaan FluidSynth.**
Kalau playback jalan dari file `.mid`, maka transpose dan metronome berarti tulis ulang file lalu reload, dan posisi playback hilang. Dengan `Sequencer` + jendela lookahead ~300 ms, ketiga fitur itu turun jadi parameter: thread Python mengisi antrian di depan playhead, FluidSynth pegang jamnya, perubahan parameter cukup membuang antrian di depan "sekarang" lalu menjadwalkan ulang.

**K2 — `time_scale` dibiarkan default (1000 tick/detik = milidetik).**
Tempo diurus di pemetaan tick→ms milik kita sendiri. Mengubah `time_scale` saat ada event terjadwal akan menggeser event itu juga.

**K3 — Timeline datar sebagai kontrak bersama.**
Pohon `Bar → Voice → Beat → Note` milik GPIF tidak cocok untuk `.mid`, yang notnya bebas di tick manapun. Jadi `_PlayedNote` di `convert.py` dinaikkan jadi representasi publik: **daftar not datar + grid bar**. Scheduler, piano roll, dan ketiga eksporter hanya kenal itu. Tiap importer bertanggung jawab menghasilkannya.
Konsekuensi baik: impor `.mid` **tidak perlu kuantisasi sama sekali**, karena tidak ada notasi yang harus digambar.

**K4 — Tempo UI adalah pengali, bukan BPM absolut.**
Slider 70% berarti 0.7 × tempo lagu. Lagu yang temponya berubah di tengah tetap benar.

**K5 — Transpose tidak menyentuh track drum.**
Di channel 10 nomor not adalah ID instrumen, bukan pitch. `Track.is_drums` sudah ada di model.

**K6 — Export MP3 memakai scheduler yang sama dengan playback.**
Synth kedua tanpa audio driver, `Sequencer.process()` diputar manual lebih cepat dari realtime, sampel ditarik via `get_samples()`. Jaminan "yang diekspor = yang didengar" datang dari konstruksi, bukan dari menjaga dua jalur kode tetap sinkron.

**K7 — Export MIDI gabungan = SMF type 0, channel tetap terpisah.**
"1 track gabungan" ditafsirkan sebagai satu MTrk berisi semua event, bukan satu channel. Menyatukan ke satu channel akan membuat semua instrumen berbunyi sama — itu kehilangan data, bukan penggabungan. Writer yang ada sudah menulis type 0 saat jumlah track = 1.

**K8 — Export mengikuti state mixer.**
Transpose, tempo, mute/solo, dan volume yang sedang aktif ikut terekspor. Metronom punya checkbox sendiri di dialog export, default mati.

## 6. Urutan pengerjaan

Prinsipnya **risiko dulu, GUI terakhir**. Tiap fase bisa diuji dari CLI tanpa GUI, jadi bug audio tidak pernah tercampur bug Qt.

### Fase 0 — selesai
Parser GPIF, model skor, SMF writer, CLI `info`/`convert`/`check`. 29 test lolos. Terverifikasi di file 148 bar × 5 track: semua durasi beat pas, semua note_on berpasangan note_off.

### F1 — Export MIDI gabungan · ~0.5 hari
Dikerjakan pertama karena paling kecil, tanpa dependensi baru, **dan jadi prasyarat MP3**.
- `to_midi_merged()` → SMF type 0, semua track jadi satu MTrk, channel dipertahankan
- CLI: `convert --merge`
- **Selesai kalau:** mido membaca hasilnya sebagai type 0, 1 track; jumlah not == total semua track; tidak ada not menggantung

### F2 — Timeline datar + playback realtime · ~3 hari ← risiko utama
- Naikkan `_PlayedNote` jadi API publik (K3); scheduler & eksporter pindah ke sana
- Pembungkus Synth/Sequencer dengan validasi argumen sendiri (README pyfluidsynth: *"will segfault/crash if you call the functions incorrectly"*)
- Thread lookahead 300 ms, pemetaan tick→ms
- Transport: play / pause / stop / seek
- Pemilihan driver: `coreaudio` (macOS), `pulseaudio` → fallback `alsa` (Linux)
- CLI: `play FILE [--from BAR]`
- **Selesai kalau:** lagu 4 menit main penuh tanpa drift (akhir ±50 ms dari durasi hitungan) dan tanpa xrun/putus

### F2.5 — Spike bundling · ~0.5 hari
Build PyInstaller minimal yang **cuma** bunyikan satu not, lalu jalankan di mesin bersih (container Linux tanpa FluidSynth, dan Mac Intel tanpa Homebrew). Sekali pakai, lalu dibuang. Tujuannya satu: buktikan `libfluidsynth` ikut terbawa **sebelum** ada 3000 baris kode di atasnya. Lihat R1.
- **Selesai kalau:** bunyi keluar di mesin yang belum pernah dipasangi FluidSynth

### F3 — Parameter realtime · ~2 hari
- Tempo (pengali, K4), transpose per track + global (kecualikan drum, K5)
- Mute / solo / volume per track via CC7
- Metronom: channel sendiri, event dibangkitkan dari grid bar, aksen di ketukan 1 — ikut benar di bar 2/4
- Reschedule-on-change: buang antrian setelah "sekarang", **kirim all-notes-off**, jadwalkan ulang
- CLI flag untuk tiap parameter
- **Selesai kalau:** ubah keempat parameter berulang-ulang saat lagu main, nol not nyangkut

### F4 — Export MP3 + WAV · ~1 hari
Murah karena F1–F3 sudah berdiri dan tidak ada dependensi native baru.
- Synth offline tanpa driver, loop `get_samples()` + `Sequencer.process()` manual
- WAV lebih dulu (tanpa encoder sama sekali), lalu MP3 via lameenc
- `synth.sample-rate` wajib sama dengan sample rate yang dikonfigurasi di lameenc
- Default: 44100 Hz, stereo, 192 kbps
- **Selesai kalau:** durasi MP3 == durasi playback ±50 ms; render lebih cepat dari realtime; file terbuka di ffprobe dan pemutar HP

### F5 — GUI mixer · ~3 hari
Lapisan tipis di atas F2–F3; tidak ada logika musik di sini.
- Daftar track: nama, instrumen, M/S, volume, transpose, VU meter
- Transport + posisi bar, checkbox metronom, slider tempo, transpose global
- Buka file, dialog export
- **Selesai kalau:** seluruh skenario di §3 bisa dijalankan tanpa menyentuh CLI

### F6 — Piano roll · ~2 hari
- QGraphicsView, warna per track, playhead mengikuti posisi
- Klik untuk seek, zoom horizontal
- **Selesai kalau:** 2000 not tergambar, scroll dan playhead tetap 60 fps

### F7 — Importer `.mid` · ~1 hari
- mido → timeline datar; grid bar dari meta time signature
- Nama track dari meta, instrumen dari program change, channel 10 → drum
- Tanpa kuantisasi (K3)
- **Selesai kalau:** hasil export MIDI dari aplikasi ini bisa diimpor balik dan identik secara audio (round-trip)

### F8 — Importer `.gp5` · ~2 hari
- Adapter PyGuitarPro → model
- **Beda penting dari GPIF:** gp5 tidak memberi nomor MIDI. Pitch harus dihitung `tuning[string] + fret`; untuk drum, `value` sudah nomor perkusi GM
- **Selesai kalau:** file gp5 yang sama (diekspor dari GP sebagai gp5 dan gp7) menghasilkan not identik dari kedua importer

### F9 — Bundling · ~3 hari
Hasil spike F2.5 dirapikan jadi build yang bisa diulang.
- Linux: PyInstaller → AppImage; `libfluidsynth` + dependensinya di-`--add-binary`, client lib audio sistem **tidak** dibundel
- macOS: PyInstaller → .app → .dmg, target x86_64, PySide6 pin 6.9.x
- Soundfont ikut di dalam bundle
- **Selesai kalau:** jalan di Ubuntu LTS bersih dan Mac Intel bersih, tanpa pasang apa pun

**Milestone:** M1 = F1–F4 (bisa dipakai dari CLI, sudah bisa ekspor) · M2 = +F5–F6 (aplikasi utuh) · M3 = +F7–F9 (lengkap & bisa dibagikan)

Total kasar ~18 hari kerja. Porsinya: playback + parameter 5.5 hari, GUI 5 hari, bundling 3.5 hari, importer 3 hari, export 1.5 hari.

## 7. Risiko

| # | Risiko | Mitigasi |
|---|---|---|
| R1 | **PyInstaller tidak mendeteksi `libfluidsynth`.** Terkonfirmasi dari source: pyfluidsynth pakai `CDLL` + `find_library`. PyInstaller hanya mendeteksi ctypes dari string literal nama file polos, dan dokumentasinya sendiri menyatakan tidak ada jaminan library ketemu saat runtime | `--add-binary` manual **beserta dependensi dylib-nya**, yang PyInstaller tidak selalu telusuri. Spike F2.5 lebih dulu, bukan setelah semua kode jadi |
| R2 | pyfluidsynth segfault kalau argumen salah (peringatan di README-nya sendiri) | Pembungkus tipis dengan validasi tipe/rentang di F2. Crash native tidak bisa di-`try/except` |
| R3 | Build macOS tidak bisa cross-compile dari Linux | Perlu akses mesin macOS Intel sejak F2.5, bukan di F9 |
| R4 | PySide6 menaikkan batas versi macOS (6.12 → macOS 14+) | Pin `6.9.*`, catat di `pyproject.toml` dengan alasannya |
| R5 | Jitter scheduler di passage padat | Timing sudah di C lewat Sequencer. Kalau masih terasa, perbesar lookahead; Python hanya mengisi antrian |

## 8. Keputusan terbuka

- **Nama paket.** `gp2midi` sudah terlalu sempit untuk aplikasi player/mixer. Usul: engine tetap `gp2midi`, aplikasinya paket terpisah.
- **Soundfont default.** TimGM6mb 6 MB (bundle kecil, suara seadanya) vs FluidR3 ~140 MB (jauh lebih baik, bundle berat). Usul: bundel yang kecil, sediakan menu untuk menunjuk SF2 sendiri.
- **Loop section** untuk latihan (ulang bar 17–24 terus-menerus) tidak ada di daftar fitur, padahal untuk latihan ini biasanya lebih berguna daripada transpose. Perlu diputuskan masuk M2 atau ditunda.
