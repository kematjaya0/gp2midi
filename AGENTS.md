# AGENTS.md

## Peran

Kamu melanjutkan engine dan aplikasi ini mengikuti `PRD.md`. Fase dikerjakan berurutan. Sebuah fase selesai ketika kriteria "Selesai kalau" di PRD §6 terpenuhi **dan** `tools/verify.sh` lolos — bukan ketika kodenya jalan sekali.

Kalau sebuah fase ternyata terhalang, selesaikan sisa fase itu sepenuhnya, lalu katakan bagian mana yang ditinggalkan dan kenapa. Mengecilkan lingkup adalah keputusan pemilik project, bukan keputusanmu.

## Orientasi

- **`PRD.md` §5** — keputusan arsitektur K1–K8 beserta alasannya. Baca sebelum menyentuh scheduler, tempo, transpose, atau jalur export; K3 (timeline datar) dan K5 (transpose lewati drum) yang paling sering dilanggar tanpa sadar.
- **`PRD.md` §6** — urutan fase dan kriteria selesai tiap fase.
- **`PRD.md` §7** — risiko yang sudah terkonfirmasi, bukan dugaan. R1 menentukan kapan bundling disentuh.
- **`README.md`** — struktur format GPIF, dan daftar apa yang sudah/belum diterjemahkan ke MIDI.
- **`gp2midi/model.py`** — satu-satunya kontrak antar lapisan. Importer mengisinya; scheduler, piano roll, dan eksporter hanya membacanya.

## Constraint

Sepuluh hal yang tidak diakui file mana pun. Tujuh yang pertama sudah pernah menjebak. Tiga yang terakhir soal playback dan belum pernah menjebak kita — ketemu saat pengukuran 2026-10-27 (FluidSynth 2.3.4 + pyfluidsynth 1.4.0), bukan saat menebak-nebak bug — dan justru itu alasannya dicatat di sini: gejala ketiganya menunjuk ke arah yang salah.

**Pool GPIF milik bersama.** `Beats`, `Notes`, dan `Rhythms` adalah pool yang dirujuk lewat id dan dipakai berulang — satu `Beat` bisa muncul di puluhan bar. Bangun objek baru per kemunculan, seperti `build_beat` sekarang. Mengubah objek pool di tempat akan merembet ke seluruh lagu sekaligus.

**Pitch punya dua sumber yang berbeda.** GPIF sudah menyediakan `Property name="Midi"` berisi nomor MIDI konser siap pakai, termasuk untuk drum — pakai itu. gp3/gp4/gp5 tidak punya properti itu; di sana pitch dihitung `tuning[string] + fret`, dan untuk drum `value` sudah berupa nomor perkusi GM.

**Drum bukan pitch.** Nomor not di channel 10 adalah ID instrumen. Transpose dan operasi pitch apa pun melewati track yang `is_drums`; menaikkan +2 akan mengubah snare jadi tom.

**PPQ 960 menanggung beban.** Pada angka itu triplet jatuh di 640 tick dan not 1/32 di 120 tick, keduanya bulat. Mengubah PPQ membuat tuplet dibulatkan dan bar tidak lagi terisi pas — invarian di §Verifikasi langsung jebol.

**Engine core nol dependensi.** Modul di `gp2midi/` hanya mengimpor stdlib; itu alasan SMF writer ditulis tangan. Lapisan aplikasi — playback, audio, nanti GUI — tinggal di subpaket `gp2midi/play/`, dan **hanya di situ** dependensi native boleh ada. (Keputusan pemilik project 2026-10-27: satu paket, namanya tetap `gp2midi`, bukan paket terpisah seperti usul awal di `PRD.md` §8.) `info`, `convert`, dan `check` wajib tetap jalan di mesin yang belum pernah dipasangi FluidSynth, jadi satu-satunya sambungan ke `gp2midi/play/` adalah import **di dalam fungsi**, bukan di kepala modul. Setiap dependensi baru wajib punya wheel `macosx_*_x86_64` karena target mencakup Mac Intel. Batas ini dijaga `tests/test_no_native_deps.py`.

**pyfluidsynth itu ctypes.** Argumen yang salah menghasilkan segfault, dan segfault tidak bisa ditangkap `try/except` — proses mati tanpa traceback. Validasi tipe dan rentang di batas pembungkus, sebelum nilai menyeberang ke C.

**Note-off mendahului note-on pada tick yang sama.** `MidiTrack.ORDER_*` yang menjamin ini. Kalau urutannya tertukar, not berulang pada pitch yang sama akan saling mematikan.

**Channel tanpa pemilihan instrumen itu bisu.** Di file `.mid` cukup ada event program change, dan pemutar mana pun paham. FluidSynth tidak menebak: channel yang belum pernah di-`program_select` tidak mengeluarkan suara sama sekali. Instrumen drum pun ada di rak (bank) terpisah bernomor **128**, bukan rak 0. Terukur dengan not snare di channel 9 — tanpa `program_select` puncak sampel **1** (bisu), bank 0 → **686** (bunyi, tapi instrumen salah), bank 128 → **2221** (benar). Drum yang bisu terbaca seperti parser salah atau soundfont tanpa drum; padahal satu panggilan yang belum ada.

**Antrian sequencer tidak bisa dibatalkan lewat pyfluidsynth.** Playback menitipkan not ~300 ms di depan playhead, supaya jamnya dipegang C dan bukan Python. Konsekuensinya: saat stop, pause, atau seek, titipan itu harus dibuang. `fluid_sequencer_remove_events` ada di library C tapi **tidak di-bind** oleh pyfluidsynth 1.4.0 — bind sendiri lewat `fluidsynth.cfunc`. Lanjutannya yang paling sering terlewat: membuang antrian **tidak** mematikan not yang sudah berbunyi, karena perintah matinya ikut terbuang. Jadi buang antrian selalu disusul all-notes-off untuk 16 channel. Kalau tidak, ada nada mendengung terus setelah stop, dan itu terbaca seperti salah hitung durasi not.

**`ORDER_*` tidak melindungi jalur playback.** Jaminan note-off mendahului note-on hanya berlaku di `smf.py`, saat menulis file. Di sequencer waktunya dibulatkan ke milidetik dan tidak ada aturan urutan sama sekali: kalau pitch yang sama dipetik dua kali dan note-off yang lama jatuh di milidetik yang sama dengan note-on yang baru, not baru bisa mati seketika. Penjadwal wajib menggeser note-off minimal 1 ms di atas note-on. Gejalanya not yang kadang hilang di passage berulang cepat — mudah tertukar dengan dugaan jitter scheduler (R5), padahal penyebabnya pembulatan.

## Verifikasi

```
tools/verify.sh
```

Empat tingkat: unit test, invarian korpus, oracle, lalu playback. Tingkat keempat (senyap, dijalankan oleh `.venv-app`): set `VERIFY_PLAYBACK=1` untuk memainkan lagu penuh (±255 detik) dan mengukur drift, tanpa env var itu cukup cuplikan 20 detik.

**Aturan oracle:** hasil `gp2midi.smf` tidak pernah divalidasi oleh pembaca kita sendiri. mido yang memutuskan file itu sah. Pembungkus yang menguji dirinya sendiri hanya membuktikan ia konsisten, bukan benar.

**Invarian korpus:** jumlah durasi beat tiap voice harus sama persis dengan panjang bar menurut time signature-nya. Properti ini yang paling cepat menangkap kesalahan aritmetika ritme, dan `gp2midi check` menguji seluruh bar di seluruh track.

**Yang korpus `media/` belum tutup — sudah diukur, bukan dugaan.** Ketiga file nyata ternyata sangat seragam: nol grace note, nol repeat, nol alternate ending, nol section, **setiap bar hanya satu voice** (315, 370, dan 740 bar-per-track, semuanya), satu tuplet di seluruh korpus, 11 augmentation dot, dan dinamika **hanya `F`** — 6233 beat, tanpa satu pun pengecualian. Artinya ekspansi repeat, alternate ending, voice jamak, dan pemetaan velocity bertumpu **sepenuhnya** pada fixture sintetis di `tests/fixture.py`. Kalau kamu menyentuh salah satu dari itu, menjalankan korpus tidak membuktikan apa pun — tambahkan kasus ke fixture. Korpus juga belum punya file gp5 maupun `.mid`.

## Konvensi

- Komentar dan docstring Bahasa Indonesia; identifier, nama kelas, dan nama fungsi Inggris.
- Komentar menjelaskan alasan, bukan menerjemahkan kode yang sudah jelas.
- `from __future__ import annotations` di tiap modul; type hint gaya `X | None`.
- Model dipegang `dataclass`, bukan `dict`.
- Test pakai `unittest` dengan fixture GPIF sintetis, supaya rangkaian test tidak bergantung pada file tab berhak cipta. File di `media/` adalah korpus lokal, bukan bagian dari test suite.
