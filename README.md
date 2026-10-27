# gp2midi

Player, mixer, dan konverter Guitar Pro untuk latihan musik tanpa Guitar Pro.

Project ini ditujukan untuk membuka lagu, mendengarkan tiap track, mengatur tempo dan nada, memakai metronom, lalu mengekspor hasil latihan ke MIDI, WAV, atau MP3. Engine saat ini sudah dapat membaca Guitar Pro 7/8 (`.gp`/`.gpif`), menulis MIDI, dan melakukan playback realtime melalui FluidSynth. GUI serta sebagian fitur mixer masih dalam pengembangan.

> Status: **alpha / aktif dikembangkan**. CLI engine dan playback sudah tersedia. Lihat [Status pengembangan](#status-pengembangan).

## Tujuan

Alur utama yang ditargetkan:

1. Buka file Guitar Pro atau MIDI.
2. Solo track yang ingin dipelajari.
3. Perlambat tempo tanpa mengubah pitch.
4. Transpose ke kunci yang nyaman.
5. Aktifkan metronom.
6. Ekspor audio untuk latihan di perangkat lain.

Project ini bukan editor notasi. Musik hanya dibaca dan dimainkan; tidak ada penyuntingan not, tablatur, atau penulisan kembali ke format Guitar Pro.

## Fitur

### Sudah tersedia

- Membaca Guitar Pro 7/8 (`.gp`) dan GPIF mentah (`.gpif`).
- Menampilkan metadata, tempo, tuning, instrumen, dan jumlah not.
- Memvalidasi durasi beat terhadap time signature.
- Mengembangkan repeat dan alternate ending ke timeline linear.
- Mengekspor MIDI dalam tiga mode:
  - SMF type 1 multi-track;
  - satu SMF type 0 per track;
  - satu SMF type 0 gabungan dengan channel instrumen tetap terpisah.
- Playback realtime berbasis FluidSynth.
- Transport playback: mulai dari bar tertentu, pause, stop, dan seek pada API playback.
- Timeline datar sebagai kontrak bersama antara importer, scheduler, dan exporter.
- Timing scheduler di C melalui `fluidsynth.Sequencer`, dengan lookahead sekitar 300 ms.
- Docker Compose untuk development, test, verifikasi, dan playback pada host Linux/PulseAudio.

### Direncanakan

- Tempo realtime sebagai pengali tempo lagu.
- Transpose global dan per track; track drum tidak ikut ditranspose.
- Mute, solo, volume, pan, dan metronom.
- Ekspor WAV dan MP3 sesuai state mixer.
- GUI desktop dengan PySide6.
- Piano roll berbasis QGraphicsView.
- Import MIDI tanpa kuantisasi.
- Import Guitar Pro 3/4/5 melalui PyGuitarPro.
- Bundle AppImage Linux serta `.app`/`.dmg` macOS Intel.

## Bukan lingkup project

- Menulis atau mengedit not.
- Menampilkan notasi balok atau tablatur.
- Menulis kembali file Guitar Pro.
- EQ, reverb, kompresi, atau mixing lanjutan.
- Playback artikulasi kontinu seperti bend, slide, vibrato, trill, dan tremolo picking.

## Persyaratan

- Python 3.10 atau lebih baru.
- Untuk konversi dan inspeksi: tanpa dependensi runtime tambahan.
- Untuk playback:
  - FluidSynth 2.x;
  - `pyfluidsynth==1.4.0`;
  - NumPy;
  - soundfont `.sf2` seperti TimGM6mb.

Target platform akhir: Linux x86_64 dan macOS Intel x86_64.

## Instalasi

### Engine CLI

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Perintah `info`, `convert`, dan `check` tetap berfungsi tanpa FluidSynth.

### Playback

Pasang library FluidSynth dari package manager sistem, lalu instal extra `play`:

```bash
.venv/bin/pip install -e '.[play]'
```

Untuk setup development yang dipakai project:

```bash
python3 -m venv .venv-app
.venv-app/bin/pip install -e '.[play]'
```

Soundfont dicari pada lokasi sistem umum. Path lain dapat diberikan lewat `--soundfont`.

## Pemakaian

### Informasi skor

```bash
gp2midi info "lagu.gp"
gp2midi info "lagu.gp" --json
```

### Validasi ritme

```bash
gp2midi check "lagu.gp"
```

Perintah ini memeriksa bahwa total durasi beat setiap voice tepat mengisi panjang bar menurut time signature.

### Ekspor MIDI

```bash
# SMF type 1: satu MTrk per track, plus track konduktor
gp2midi convert "lagu.gp" -o lagu.mid

# SMF type 0 terpisah untuk setiap track
gp2midi convert "lagu.gp" --split -o ./stems

# SMF type 0 gabungan: satu MTrk, channel instrumen dipertahankan
gp2midi convert "lagu.gp" --merge -o lagu-merged.mid
```

Opsi konversi:

| Opsi | Keterangan |
|---|---|
| `-o, --output PATH` | File tujuan; folder tujuan pada mode `--split` |
| `--split` | Tulis satu file MIDI type 0 per track |
| `--merge` | Gabungkan semua track dalam satu MTrk type 0 |
| `--gate N` | Pengali panjang not; default `1.0` |
| `--include-empty` | Sertakan track tanpa not |
| `--no-expand-repeats` | Abaikan repeat dan alternate ending |

`--split` dan `--merge` tidak dapat digunakan bersamaan.

### Playback realtime

```bash
# mainkan seluruh lagu
.venv-app/bin/gp2midi play "lagu.gp"

# mulai dari bar ke-33
.venv-app/bin/gp2midi play "lagu.gp" --from 33

# ukur akurasi scheduler selama 20 detik tanpa suara
.venv-app/bin/gp2midi play "lagu.gp" --silent --seconds 20 --report
```

Opsi playback:

| Opsi | Keterangan |
|---|---|
| `--from BAR` | Mulai dari bar playback tertentu; 1-based |
| `--seconds N` | Berhenti setelah N detik |
| `--soundfont PATH` | Gunakan soundfont `.sf2` tertentu |
| `--driver NAME` | Paksa driver audio FluidSynth |
| `--gain N` | Gain FluidSynth `0.0`–`10.0`; default `0.5` |
| `--silent` | Gain nol; jam realtime tetap berjalan |
| `--report` | Cetak drift dan event terlambat; gagal bila drift melebihi 50 ms |
| `--gate N` | Pengali panjang not |
| `--no-expand-repeats` | Abaikan repeat dan alternate ending |

Driver default: `coreaudio` pada macOS; `pulseaudio`, lalu fallback `alsa`, pada Linux.

## API Python

```python
from gp2midi import parse, to_midi
from gp2midi.convert import Options

score = parse("lagu.gp")
print(score.title)
print([track.name for track in score.tracks])

to_midi(score, "lagu.mid", Options(gate=0.95))
```

`parse()` menghasilkan model netral dari `gp2midi/model.py`. Importer mengisi model; timeline, scheduler, dan exporter hanya membacanya.

## Arsitektur

```text
.gp / .gpif
     │
     ▼
 GPIF importer ──► model skor ──► timeline datar
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
              MIDI exporter                   FluidSynth scheduler
                                                      │
                                                      ▼
                                               audio realtime
```

Keputusan utama:

- **Timeline datar.** Scheduler, piano roll, dan exporter memakai daftar not datar serta grid bar. Format MIDI tidak perlu dikuantisasi ke struktur notasi.
- **PPQ 960.** Triplet dan not 1/32 tetap memiliki panjang tick bulat.
- **Scheduler sendiri.** `fluidsynth.Sequencer` memungkinkan seek, tempo, transpose, dan metronom tanpa menulis ulang file MIDI.
- **Tempo berupa pengali.** Perubahan tempo asli di tengah lagu tetap dipertahankan.
- **Drum bukan pitch.** Transpose tidak boleh mengubah track drum.
- **Satu jalur playback/export audio.** Export audio dirancang memakai scheduler yang sama agar hasil ekspor sama dengan yang didengar.
- **Engine nol dependensi.** Dependensi native hanya boleh berada di `gp2midi/play/` dan diimpor secara lazy.

### Struktur project

```text
gp2midi/             engine, model, parser, timeline, MIDI writer
gp2midi/play/        pembungkus FluidSynth dan scheduler realtime
tests/               unit test berbasis fixture GPIF sintetis
tools/               verifikasi korpus, oracle MIDI, dan playback
media/               korpus lokal; bukan bagian test suite
PRD.md               kebutuhan, keputusan arsitektur, roadmap
```

## Format dan pemetaan musik

File `.gp` Guitar Pro 7/8 adalah arsip ZIP. Data musik dibaca dari `Content/score.gpif`; data layout diabaikan.

- Pool `Beats`, `Notes`, dan `Rhythms` dapat dipakai berulang. Parser membuat objek baru untuk setiap kemunculan agar state tidak bocor antar bar.
- Pitch GPIF diambil dari `Property name="Midi"`, termasuk nomor perkusi drum.
- Track drum dipetakan ke channel 10.
- Program, bank, volume, dan pan diterjemahkan ke event MIDI.
- Tie digabung menjadi satu not, termasuk lintas bar.
- Hingga empat voice per bar dimainkan dari awal bar yang sama.
- Dinamika `PPP`–`FFF` dipetakan ke velocity.
- Grace note mencuri waktu dari beat berikutnya tanpa menggeser batas bar.
- Note-off selalu ditulis sebelum note-on pada tick yang sama.

Belum diterjemahkan ke playback: bend, slide, vibrato, trill, tremolo picking, let-ring, tempo ramp linear, fermata, free time, D.C., dan Coda.

## Development

### Test

```bash
python3 -m unittest discover -s tests -t .
```

Test memakai `unittest` dan fixture GPIF sintetis; tidak bergantung pada file tab berhak cipta.

### Verifikasi penuh

```bash
tools/verify.sh
```

Verifikasi mencakup:

1. unit test;
2. invarian durasi seluruh korpus;
3. validasi file MIDI memakai `mido` sebagai oracle independen;
4. playback senyap dan pengukuran drift bila `.venv-app` tersedia.

Uji lagu penuh:

```bash
VERIFY_PLAYBACK=1 tools/verify.sh
```

### Docker Compose

```bash
docker compose build
docker compose run --rm dev
docker compose run --rm test
docker compose run --rm verify
```

Playback dari container hanya didukung pada host Linux dengan socket PulseAudio:

```bash
docker compose --profile audio run --rm playback "lagu.gp"
docker compose --profile audio run --rm playback "lagu.gp" --silent --seconds 15 --report
```

Source di-bind-mount ke `/work`. Venv host disembunyikan dari container karena binary venv host tidak portabel.

## Status pengembangan

| Fase | Status | Hasil |
|---|---|---|
| F0 | Selesai | Parser GPIF, model, SMF writer, `info`/`convert`/`check` |
| F1 | Selesai | Export MIDI gabungan SMF type 0 |
| F2 | Selesai | Timeline datar dan playback realtime |
| F2.5 | Selesai di Linux | Spike PyInstaller lolos pada Ubuntu bersih; macOS Intel belum diuji |
| F3 | Berikutnya | Tempo, transpose, mute/solo/volume, metronom |
| F4 | Belum | Export WAV dan MP3 |
| F5 | Belum | GUI mixer |
| F6 | Belum | Piano roll |
| F7 | Belum | Importer MIDI |
| F8 | Belum | Importer GP3/GP4/GP5 |
| F9 | Belum | Bundle distribusi Linux dan macOS |

Milestone:

- **M1:** CLI playback, parameter realtime, dan export audio — F1–F4.
- **M2:** aplikasi desktop lengkap — F5–F6.
- **M3:** importer tambahan dan bundle distribusi — F7–F9.

## Batasan saat ini

- Input produksi baru `.gp` Guitar Pro 7/8 dan `.gpif` mentah.
- Playback membutuhkan FluidSynth serta soundfont lokal.
- Playback Docker hanya bekerja pada host Linux/PulseAudio.
- Bundle macOS Intel belum diverifikasi; build macOS tidak dapat dilakukan dari Linux.
- Channel MIDI yang sama pada dua track dapat membatasi independensi program dan controller; CLI melaporkan collision saat mode `--merge`.

Detail kebutuhan, keputusan teknis, kriteria selesai tiap fase, dan risiko tersedia di [`PRD.md`](PRD.md). Hasil spike bundling Linux tersedia di [`F2.5-BUNDLING-REPORT.md`](F2.5-BUNDLING-REPORT.md).

## Lisensi

Lisensi belum ditentukan.
