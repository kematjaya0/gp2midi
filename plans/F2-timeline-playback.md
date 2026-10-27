# F2 — Timeline datar + playback realtime

Fase kedua di `PRD.md` §6. Estimasi 3 hari. **Ini fase risiko utama**: dependensi native pertama masuk di sini.

Kerjakan **Langkah 0 sampai 9 berurutan**. Tiap langkah punya perintah verifikasi dan output yang diharapkan. Jangan lanjut ke langkah berikutnya sebelum verifikasi langkah itu lolos. Kalau macet, lihat §Kalau macet di bawah — berhenti dan laporkan, jangan menebak.

## Baca dulu

1. `AGENTS.md` — seluruhnya. Pendek.
2. `PRD.md` keputusan **K1, K2, K3, K5** dan risiko **R2, R5**.
3. `gp2midi/convert.py` — `_PlayedNote`, `_track_notes`, `playback_order`, `_bar_starts`, `_assign_channels`. Semua itu dipindah di fase ini.

Constraint dari `AGENTS.md` yang kena di fase ini:

- **Engine core nol dependensi.** Aturannya sekarang per-direktori: `gp2midi/*.py` tetap stdlib murni, dan seluruh dependensi native masuk ke subpaket baru `gp2midi/play/`. Lihat Keputusan 1.
- **Drum bukan pitch.** Channel 10 (index 9) tidak pernah di-transpose. Di fase ini belum ada transpose, tapi pemilihan program drum punya jebakannya sendiri — lihat fakta F-5.
- **pyfluidsynth itu ctypes.** Argumen salah = segfault, tidak bisa di-`try/except`. Validasi di batas pembungkus (Langkah 4 dan 5), bukan di pemanggil.
- **PPQ 960 menanggung beban.** Jangan ubah.
- **Note-off mendahului note-on pada tick yang sama.** Di SMF itu dijamin `MidiTrack.ORDER_*`. Di sequencer tidak ada jaminan serupa; lihat Langkah 6 poin 5.

---

## Fakta yang sudah diukur di mesin ini

Semua ini **sudah dijalankan dan dikonfirmasi** pada 2026-10-27. Jangan uji ulang dari nol, dan jangan menggantinya dengan dugaan.

**F-1 Versi.** `libfluidsynth.so.3` = FluidSynth **2.3.4** di `/lib/x86_64-linux-gnu/`. `ctypes.util.find_library("fluidsynth")` → `libfluidsynth.so.3`. `pip install pyfluidsynth` → **1.4.0**, `fluidsynth.api_version == "1.4.0"`. pyfluidsynth menuntut **numpy** (dipakai `get_samples`). Python sistem 3.12.3.

**F-2 `Sequencer` tidak punya `remove_events`.** pyfluidsynth 1.4.0 hanya mengekspor `delete, get_tick, note, note_off, note_on, process, register_client, register_fluidsynth, timer`. `fluid_sequencer_remove_events` **tidak di-bind**, padahal itu satu-satunya cara membatalkan event yang sudah dijadwalkan — dibutuhkan untuk stop, pause, dan seek. Bind sendiri; kode yang sudah teruji ada di Langkah 5.

**F-3 Driver audio.** `pulseaudio` dan `alsa` dua-duanya berhasil dibuka di mesin ini (`Synth.start(driver=...)` tanpa exception). Peringatan `fluidsynth: warning: Failed to set thread to high priority` **normal** dan bukan kegagalan — muncul karena user tidak punya limit realtime. Jangan perlakukan sebagai error.

**F-4 Jam sequencer akurat, tapi API-nya diberi label deprecated.** Dengan `Sequencer(time_scale=1000, use_system_timer=True)` selisih `get_tick()` terhadap `time.monotonic()` diukur **min -0.4 ms, max +0.5 ms** selama 6 detik. FluidSynth 2.3.4 mencetak sekali `warning: sequencer: Usage of the system timer has been deprecated!`. Peringatan itu **diterima**: timer sistem berjalan di C, dan itu yang dimaksud K1 dengan "bebas jitter GIL". Alternatifnya (`use_system_timer=False` + `process()` dari Python) memindahkan ketepatan waktu not ke periode loop Python — justru yang K1 hindari. Jadi: **realtime pakai timer sistem** (F2 ini); **render offline** nanti pakai `use_system_timer=False` + `process()` (F4), dan itu sebabnya `Audio` di Langkah 5 menyembunyikan sumber jam di balik satu method `now()`.

**F-5 Channel drum senyap tanpa `program_select` bank 128.** Diukur dengan `TimGM6mb.sf2`, not 38 (snare) di channel 9, puncak sampel absolut:

| perlakuan channel 9 | puncak |
|---|---|
| tanpa `program_select` sama sekali | **1** (senyap) |
| `program_select(9, sfid, 0, 0)` | 686 (preset melodis, suara salah) |
| `program_select(9, sfid, 128, 0)` | **2221** (benar) |

Artinya: setiap channel yang dipakai **wajib** di-`program_select`, dan channel drum wajib bank **128**. `program_select` mengembalikan `-1` (`fluidsynth.FLUID_FAILED`) kalau bank/preset tidak ada — ia mencetak error ke stderr tapi **tidak** crash, jadi fallback aman.

**F-6 Soundfont tersedia.** `/usr/share/sounds/sf2/TimGM6mb.sf2` dan `/usr/share/sounds/sf2/default-GM.sf2` ada di mesin ini.

**F-7 Semua track korpus pakai bank 0.** `bank_msb == bank_lsb == 0`, `volume == 0.8`, `pan == 0.5` di ketiga file. Jadi jalur bank non-nol **tidak tertutup korpus** — kalau kamu menulis logika bank, ia hanya diuji fixture.

**F-8 Durasi yang benar, untuk mencocokkan hasilmu.** `end_tick` = akhir bar terakhir; `last_note_end` = tick note-off terakhir. Kolom "mido" adalah `MidiFile.length` dari hasil `convert` biasa, dibaca parser independen.

| file | end_tick | last_note_end | ms(last_note_end) | mido (ms) |
|---|---|---|---|---|
| `Raim Laode-Lesung Pipi…` | 241920 | 241920 | 222352.9 | 222353.0 |
| `Tiara Andini…Lagu Pernikahan Kita…` | 566400 | 548160 | 244714.3 | 244714.0 |
| `seventeen-Menemukanmu…` | 282240 | 282240 | 254742.9 | 254742.9 |

Dua hal penting dari tabel ini:

- Peta tick→ms yang benar **cocok dengan mido sampai di bawah 1 ms**. Itu dipakai sebagai oracle di Langkah 3.
- `Lagu Pernikahan Kita` punya **18240 tick bar kosong di ekor**. Jadi durasi playback diukur sampai `last_note_end`, **bukan** `end_tick`. Kalau kamu pakai `end_tick`, file itu akan tampak drift 8 detik.
- `Menemukanmu` berdurasi 254.7 detik = lagu "4 menit" yang dimaksud kriteria selesai.

---

## Keputusan yang sudah diambil

Jangan putuskan ulang, jangan tawar.

1. **Satu paket, nama tetap `gp2midi`.** Keputusan pemilik project 2026-10-27; `PRD.md` §8 butir "nama paket" dengan ini tertutup, dan usul "aplikasinya paket terpisah" di situ **tidak** diambil. Lapisan aplikasi jadi subpaket `gp2midi/play/`, bukan paket sejajar.

   Yang menggantikan batas lama "`gp2midi/` nol dependensi": **`gp2midi/*.py` stdlib murni, dependensi native hanya boleh ada di dalam `gp2midi/play/`.** Batasnya tetap per-direktori supaya masih bisa diperiksa sekilas, dan dijaga satu test di Langkah 4b. Satu-satunya titik sambung yang diizinkan adalah import **di dalam** fungsi `_cmd_play()` di `gp2midi/cli.py` — lihat Keputusan 3.
2. **Timeline datar tinggal di engine**, di modul baru `gp2midi/timeline.py`. Ia stdlib murni dan dipakai bersama oleh eksporter (sudah ada), scheduler (fase ini), dan piano roll (F6).
3. **Satu CLI:** `python3 -m gp2midi play FILE`, sejajar `info` / `convert` / `check` — persis seperti tertulis di `PRD.md` §6 F2. Definisi argparse-nya tinggal di `gp2midi/cli.py` (stdlib, aman), eksekusinya didelegasikan lewat import di dalam fungsi:

   ```python
   def _cmd_play(args) -> int:
       from .play.cli import run   # lazy: info/convert/check tetap jalan tanpa FluidSynth
       return run(args)
   ```

   Import di dalam fungsi di sini **bukan** pelanggaran, melainkan mekanismenya: `python3 -m gp2midi convert` harus tetap jalan di mesin tanpa FluidSynth terpasang, dan itu diuji di Langkah 7.
4. **Venv aplikasi `.venv-app/`**, terpisah dari `.venv-oracle/`. pyfluidsynth dipin `==1.4.0`.
5. **`time_scale` dibiarkan 1000** (K2). Satu tick sequencer = 1 ms. Jangan diubah.
6. **Lookahead 300 ms, interval pengisian 100 ms.** Keduanya konstanta modul, bukan angka telanjang di tengah kode.
7. **note_on dan note_off satu not dijadwalkan bersamaan**, saat not itu masuk jendela lookahead. Tidak ada daftar "not yang sedang berbunyi" yang harus dipelihara.

---

## Hasil akhir

```bash
# dengar (ini yang sebenarnya dituju)
.venv-app/bin/python -m gp2midi play "media/seventeen-Menemukanmu-05-16-2026.gp"
.venv-app/bin/python -m gp2midi play "media/seventeen-Menemukanmu-05-16-2026.gp" --from 33

# ukur, tanpa suara
.venv-app/bin/python -m gp2midi play "media/seventeen-Menemukanmu-05-16-2026.gp" --silent --report
```

**Selesai kalau keenam hal ini benar:**

1. `tools/verify.sh` lolos, termasuk bagian `4/4` yang kamu tambahkan di Langkah 8.
2. Output `convert` **byte-identik** dengan baseline yang kamu rekam di Langkah 0 — ketiga mode (normal, `--merge`, `--split`). Refactor timeline tidak boleh mengubah satu byte pun.
3. 34 test lama tetap lolos, ditambah test baru dari Langkah 3, 4, dan 6.
4. `VERIFY_PLAYBACK=1 tools/verify.sh` memainkan `Menemukanmu` penuh (254.7 detik) dan melaporkan `drift <= 50 ms` serta `late_events == 0`.
5. `play --from 33` mulai di bar 33, bukan di awal; `pause` lalu `resume` tidak meninggalkan not nyangkut.
6. **Satu kali dengar oleh pemilik project.** Kamu tidak bisa mendengar. Jangan pernah menulis bahwa suaranya benar — laporkan bahwa butuh satu kali verifikasi dengar, dan sebutkan perintahnya.

---

## Langkah 0 — Venv aplikasi dan baseline byte

**0a. Venv.** Buat `.venv-app` dan pasang dependensinya:

```bash
cd /home/kematjaya/Projects/gp2midi
python3 -m venv .venv-app
.venv-app/bin/pip install --quiet "pyfluidsynth==1.4.0" numpy
.venv-app/bin/python -c "import fluidsynth; print(fluidsynth.api_version)"
```

Harapan: `1.4.0`.

**0b. `.gitignore`.** Tambahkan satu baris `.venv-app/` setelah baris `.venv-oracle/`.

**0c. Baseline byte.** Ini jaring pengaman untuk seluruh Langkah 1–2. Rekam **sebelum** menyentuh kode apa pun:

```bash
mkdir -p /tmp/f2-baseline && rm -rf /tmp/f2-baseline/*
for f in media/*.gp; do
    b=$(basename "$f")
    python3 -m gp2midi convert "$f" -o "/tmp/f2-baseline/$b.mid" >/dev/null
    python3 -m gp2midi convert "$f" --merge -o "/tmp/f2-baseline/$b.merged.mid" >/dev/null
    python3 -m gp2midi convert "$f" --split -o "/tmp/f2-baseline/$b.split" >/dev/null
done
find /tmp/f2-baseline -name '*.mid' | sort | xargs sha256sum > /tmp/f2-baseline/SUMS
wc -l < /tmp/f2-baseline/SUMS
```

Harapan: `21` (3 file × [1 normal + 1 merged + 5 split]).

Simpan juga perintah pemeriksanya, dipakai berulang nanti:

```bash
# cek-baseline: jalankan setelah tiap perubahan di Langkah 1-2
rm -rf /tmp/f2-now && mkdir -p /tmp/f2-now
for f in media/*.gp; do
    b=$(basename "$f")
    python3 -m gp2midi convert "$f" -o "/tmp/f2-now/$b.mid" >/dev/null
    python3 -m gp2midi convert "$f" --merge -o "/tmp/f2-now/$b.merged.mid" >/dev/null
    python3 -m gp2midi convert "$f" --split -o "/tmp/f2-now/$b.split" >/dev/null
done
sed 's#/tmp/f2-baseline#/tmp/f2-now#' /tmp/f2-baseline/SUMS | sha256sum -c - | grep -v ': OK$' ; echo "selisih: $?"
```

Harapan: tidak ada baris yang dicetak sebelum `selisih:`, dan angkanya `1` (artinya `grep` tidak menemukan kegagalan). Kalau ada baris `FAILED`, refactor-mu mengubah output — perbaiki di situ, jangan lanjut.

---

## Langkah 1 — `gp2midi/timeline.py`

Modul baru. **Stdlib murni.** Isinya tiga bagian: struktur data publik, peta tempo, dan pembangun timeline.

**1a. Pindahkan dari `convert.py` ke `timeline.py`, verbatim**, tanpa mengubah logikanya:

- konstanta `DRUM_CHANNEL`, `DYNAMIC_VELOCITY`, `DEAD_NOTE_TICKS`
- `class Options`
- `playback_order()`
- `_bar_starts()`
- `_velocity()`
- `_track_notes()`
- `_assign_channels()`

**1b. Dua perubahan pada yang dipindah itu**, hanya dua:

`_PlayedNote` jadi publik dan bertambah dua field:

```python
@dataclass
class PlayedNote:
    """Satu not yang benar-benar berbunyi, pada timeline yang sudah di-expand."""
    pitch: int
    start: int          # tick absolut
    end: int            # tick absolut, selalu > start
    velocity: int
    channel: int = 0    # 0-based; 9 = drum
    track: int = 0      # Track.index asalnya
```

dan `_track_notes` menerima channel + indeks track supaya bisa mengisi dua field itu:

```python
def _track_notes(track: Track, order: list[int], starts: list[int],
                 options: Options, channel: int = 0) -> list[PlayedNote]:
```

Di dalamnya, setiap pembuatan `_PlayedNote(...)` jadi `PlayedNote(note.midi, start, end, velocity, channel, track.index)`. Urutan `played.sort(key=lambda n: (n.start, n.pitch))` di akhir **tidak berubah** — kalau kuncinya berubah, baseline byte jebol.

**1c. Tambahkan `TempoMap`:**

```python
@dataclass
class TempoMap:
    """Peta tick <-> milidetik. Satu-satunya tempat konversi waktu terjadi."""
    ppq: int
    points: list[tuple[int, float]]   # (tick, bpm), urut naik, elemen pertama selalu tick 0

    @classmethod
    def from_score(cls, score: Score) -> TempoMap: ...
    def ms(self, tick: int) -> float: ...
    def tick(self, ms: float) -> int: ...
```

Aturannya:

- `from_score`: ambil `score.tempos`, urutkan naik berdasarkan tick, buang titik berturut dengan tick sama (ambil yang terakhir). Kalau kosong atau titik pertama bukan tick 0, sisipkan `(0, 120.0)` di depan. BPM `<= 0` ditolak dengan `ValueError` — bukan dibulatkan diam-diam.
- `ms`: panjang satu tick pada bpm tertentu = `60000.0 / (bpm * ppq)`. Jumlahkan per segmen sampai `tick`. Untuk `tick` sebelum 0 → kembalikan `0.0`.
- `tick`: kebalikannya, jalan per segmen, kembalikan `int` hasil pembulatan.
- `ms(self.tick(x))` tidak wajib sama persis dengan `x` (pembulatan tick), tapi selisihnya harus di bawah satu tick.

**1d. Tambahkan `BarSlot` dan `Timeline`:**

```python
@dataclass
class BarSlot:
    slot: int           # posisi pada timeline yang sudah di-expand (0-based)
    source: int         # indeks MasterBar aslinya
    start: int          # tick awal
    length: int         # panjang dalam tick
    numerator: int
    denominator: int


@dataclass
class Timeline:
    """Kontrak bersama scheduler, piano roll, dan eksporter (PRD K3)."""
    ppq: int
    end_tick: int                   # akhir bar terakhir
    bars: list[BarSlot]
    notes: list[PlayedNote]         # urut (start, pitch)
    tempo: TempoMap
    tracks: list[Track]             # referensi ke model, untuk nama/program/volume/pan
    channels: dict[int, int]        # Track.index -> channel 0-based

    @property
    def last_note_end(self) -> int:
        """Tick note-off terakhir. Ini akhir playback, bukan end_tick — lihat fakta F-8."""

    @property
    def duration_ms(self) -> float:
        """ms sampai last_note_end."""

    def bar_tick(self, number: int) -> int:
        """Tick awal bar nomor `number` (1-based, dalam urutan playback).
        Di luar rentang -> ValueError dengan pesan yang menyebut jumlah bar."""

    def notes_of(self, track_index: int) -> list[PlayedNote]:
        """Not satu track, urutannya sama dengan di self.notes."""
```

**1e. `build_timeline`:**

```python
def build_timeline(score: Score, options: Options | None = None) -> Timeline:
```

Urutannya: `options or Options()` → `playback_order` → `_bar_starts` → `_assign_channels` → bangun `bars` dari `order` + `starts` + `score.master_bars` → untuk setiap track kumpulkan `_track_notes(track, order, starts, options, channels[track.index])` dan gabung → `notes.sort(key=lambda n: (n.start, n.pitch, n.track))` → `TempoMap.from_score(score)` → kembalikan `Timeline`.

Perhatikan kunci sort global menambahkan `n.track` sebagai pemecah seri terakhir. Itu hanya memengaruhi urutan **antar** track; urutan di dalam satu track tetap `(start, pitch)`, dan itu yang menjaga baseline byte.

**Verifikasi Langkah 1:**

```bash
python3 -c "
from gp2midi.timeline import build_timeline, TempoMap
from gp2midi import parse
s = parse('media/seventeen-Menemukanmu-05-16-2026.gp')
t = build_timeline(s)
print('bars', len(t.bars), 'notes', len(t.notes))
print('end_tick', t.end_tick, 'last_note_end', t.last_note_end)
print('durasi ms', round(t.duration_ms, 1))
print('bar 1 ->', t.bar_tick(1), 'bar 33 ->', t.bar_tick(33))
print('channel', t.channels)
"
```

Harapan persis: `bars 74`, `notes 3975`, `end_tick 282240`, `last_note_end 282240`, `durasi ms 254742.9`, `bar 1 -> 0`, `channel {0: 0, 1: 1, 2: 2, 3: 9, 4: 3}`.

Kalau `notes` bukan 3975, `_track_notes` rusak saat dipindah. Kalau `durasi ms` bukan 254742.9, `TempoMap` salah — bandingkan dengan tabel F-8.

---

## Langkah 2 — `convert.py` memakai timeline

Sekarang eksporter berhenti punya jalur hitungnya sendiri.

**2a. Di `gp2midi/convert.py`**, hapus semua yang sudah dipindah di Langkah 1, lalu re-export supaya pemanggil lama tidak perlu diubah:

```python
from .timeline import (
    DEAD_NOTE_TICKS,
    DRUM_CHANNEL,
    DYNAMIC_VELOCITY,
    Options,
    PlayedNote,
    Timeline,
    build_timeline,
    playback_order,
)
```

`gp2midi/cli.py` mengimpor `Options` dan `playback_order` dari `.convert`, dan `tests/test_gp2midi.py` memakai `convert._rhythm_ticks`-style akses internal di beberapa test. **Jangan ubah `cli.py` maupun test yang ada** — re-export inilah yang membuatnya tetap jalan. Kalau sebuah test lama mengakses nama yang kamu pindah dan belum kamu re-export, tambahkan nama itu ke daftar re-export, bukan mengubah test-nya.

**2b. Ketiga eksporter memakai `Timeline`.** Pola untuk `to_midi`:

```python
def to_midi(score, out_path, options=None):
    timeline = build_timeline(score, options)
    midi_tracks = [_conductor_from(timeline, score)]
    ...
    for track in score.tracks:
        notes = timeline.notes_of(track.index)
        ...
```

`_conductor`, `_write_setup`, `_write_channel_setup`, `_emit` **tidak berubah tanda tangannya** selain `_conductor` yang sekarang boleh menerima `Timeline` ketimbang `(order, starts, end_tick)` — pilih salah satu dan konsisten di ketiga eksporter.

`to_midi_per_track` tetap memakai channelnya sendiri (`DRUM_CHANNEL` atau `0`) lewat parameter `channel` di `_emit`; jangan ganti dengan `note.channel`, karena mode split sengaja memakai channel berbeda.

**Verifikasi Langkah 2 — ini gerbang terpenting di seluruh fase:**

```bash
python3 -m unittest discover -s tests -t .      # harapan: Ran 34 tests ... OK
# lalu jalankan blok "cek-baseline" dari Langkah 0c
./tools/verify.sh                               # harapan: SEMUA LOLOS
```

Kalau ada satu saja hash yang `FAILED`, berhenti di sini. Refactor ini wajib byte-identik; perbedaan byte berarti ada perubahan perilaku yang tidak kamu sadari.

---

## Langkah 3 — Test timeline dan oracle tempo

**3a. File baru `tests/test_timeline.py`.** Header mengikuti `tests/test_gp2midi.py` (dua `sys.path.insert`, `from fixture import simple_score, write_gp`, helper `parse_fixture`).

Tulis delapan test:

1. `test_notes_match_convert` — total `len(timeline.notes)` sama dengan jumlah not dari `convert.to_midi` summary.
2. `test_notes_sorted` — `notes` naik menurut `(start, pitch, track)`.
3. `test_note_has_channel_and_track` — not drum di fixture punya `channel == 9`; not gitar `channel == 0`; `track` cocok dengan `Track.index`.
4. `test_end_tick_matches_bar_grid` — `end_tick == sum(b.length for b in bars)`, dan `bars[i].start == bars[i-1].start + bars[i-1].length` untuk semua i.
5. `test_tempo_map_quarter_note` — pada PPQ 960 dan 120 BPM, `ms(960) == 500.0`; pada 60 BPM `ms(960) == 1000.0`. Bangun `TempoMap(960, [(0, 120.0)])` langsung, tanpa fixture.
6. `test_tempo_map_change_midway` — `TempoMap(960, [(0, 120.0), (1920, 60.0)])`: `ms(1920) == 1000.0`, `ms(2880) == 2000.0`.
7. `test_tempo_map_roundtrip` — untuk beberapa tick, `abs(ms(tick(ms(t))) - ms(t))` lebih kecil dari durasi satu tick.
8. `test_bar_tick_out_of_range` — `bar_tick(0)` dan `bar_tick(len(bars) + 1)` dua-duanya `ValueError`.

Plus dua test untuk tempo yang cacat:
9. `test_tempo_zero_rejected` — `TempoMap(960, [(0, 0.0)])` → `ValueError`.
10. `test_tempo_without_zero_point_gets_default` — `TempoMap.from_score` pada skor yang tempo pertamanya di tick 480 menyisipkan `(0, 120.0)`.

**3b. Oracle untuk peta tempo: `tools/verify_tempo.py`.** Ini menutup celah "pembungkus yang menguji dirinya sendiri": durasi hasil `TempoMap` divalidasi mido, bukan oleh kode kita.

```python
#!/usr/bin/env python3
"""Oracle peta tempo: ms(last_note_end) kita vs MidiFile.length milik mido."""
# argumen: pasangan FILE.gp FILE.mid, atau satu folder; pilih yang paling sederhana
```

Isinya: untuk setiap file `.gp` di `media/`, bangun timeline, hitung `timeline.duration_ms`, lalu baca `.mid` hasil `convert` dengan mido dan bandingkan `MidiFile.length * 1000`. **Toleransi 2 ms.** Cetak satu baris per file dengan kedua angka dan selisihnya; keluar dengan status 1 kalau ada yang lewat toleransi.

Script ini dijalankan oleh **`.venv-oracle/bin/python`** (yang punya mido). Supaya `import gp2midi` berhasil dari venv itu, tambahkan di atas:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

**3c. Pasang ke `tools/verify.sh`**, di bagian `3/3`, setelah pemanggilan `verify_midi.py`:

```bash
    "$venv/bin/python" tools/verify_tempo.py "$out" || status=1
```

**Verifikasi Langkah 3:**

```bash
python3 -m unittest discover -s tests -t .      # harapan: Ran 44 tests ... OK
./tools/verify.sh                               # harapan: SEMUA LOLOS
```

Angka yang harus muncul di bagian oracle tempo, cocokkan dengan tabel F-8: selisih di bawah 1 ms untuk ketiga file. Kalau `Lagu Pernikahan Kita` menunjukkan selisih sekitar 8000 ms, kamu memakai `end_tick` padahal harusnya `last_note_end`.

---

## Langkah 4 — `gp2midi/play/validate.py`

Subpaket baru. Buat `gp2midi/play/__init__.py` (docstring saja, **kosong dari import** supaya `import gp2midi.play.validate` tidak ikut menarik `fluidsynth`) dan `gp2midi/play/validate.py`.

**`validate.py` wajib stdlib murni dan tidak mengimpor `fluidsynth`.** Itu yang membuatnya bisa diuji oleh `python3` sistem di `verify.sh` tingkat 1, tanpa venv.

Alasannya ada di R2: argumen salah ke pyfluidsynth bukan menghasilkan exception, tapi **segfault yang tidak bisa ditangkap**. Jadi nilai diperiksa di sini, sebelum menyeberang ke C.

```python
def channel(value: int) -> int:
    """0-15. Bukan int, atau di luar rentang -> TypeError / ValueError."""

def key(value: int) -> int:
    """0-127."""

def velocity(value: int) -> int:
    """0-127."""

def controller(value: int) -> int:
    """0-127."""

def control_value(value: int) -> int:
    """0-127."""

def program(value: int) -> int:
    """0-127."""

def bank(value: int) -> int:
    """0-16383."""

def sched_time(value: int) -> int:
    """Waktu absolut sequencer dalam ms: int >= 0, < 2**31."""

def gain(value: float) -> float:
    """0.0-10.0, menerima int maupun float."""

def unit(value: float) -> float:
    """0.0-1.0, untuk volume dan pan dari model."""
```

Aturan bersama untuk semua:

- `bool` **ditolak** sebagai int (`isinstance(True, int)` itu `True` di Python — jebakan nyata). Periksa `isinstance(value, bool)` lebih dulu.
- `float` ditolak di fungsi yang menuntut int, termasuk `3.0`. Pembulatan diam-diam adalah cara bug masuk ke C.
- Pesan error menyebut nama parameter, nilai yang diterima, dan rentang yang sah. Contoh: `"channel harus 0-15, dapat 16"`.
- Masing-masing **mengembalikan nilainya** supaya bisa dipakai inline: `fs.noteon(validate.channel(ch), validate.key(k), validate.velocity(v))`.

**4b. Test batas dependensi: `tests/test_no_native_deps.py`.** Ini yang menjaga Keputusan 1 sekarang setelah batasnya bukan lagi "satu direktori, nol dependensi". Dua test, dua-duanya jalan di `python3` sistem:

1. `test_core_modules_import_only_stdlib` — untuk setiap `gp2midi/*.py` (bukan isi `gp2midi/play/`), parse dengan `ast` dan pastikan tidak ada `import`/`from` yang menyebut `fluidsynth`, `numpy`, atau `gp2midi.play`. Pakai `ast`, bukan `grep` lewat subprocess, dan periksa juga import yang bersarang di dalam fungsi — kecuali satu pengecualian yang di-whitelist eksplisit: `gp2midi/cli.py` boleh `from .play.cli import run` **di dalam** `_cmd_play`. Tuliskan pengecualian itu sebagai konstanta bernama di test, dengan komentar alasannya, supaya ia jadi daftar yang disengaja dan bukan lubang.
2. `test_engine_usable_without_fluidsynth` — jalankan `[sys.executable, "-m", "gp2midi", "convert", <fixture>, "-o", <tmp>]` lewat `subprocess` dengan `fluidsynth` dan `numpy` diblokir dari `sys.modules` (sisipkan `sitecustomize`-style `-c` wrapper, atau `PYTHONPATH` berisi modul `fluidsynth.py` yang `raise ImportError`). Harus exit 0. Ini membuktikan klaim "engine jalan di mesin tanpa FluidSynth" alih-alih mengandalkan disiplin.

**File baru `tests/test_validate.py`.** Untuk tiap fungsi, uji: batas bawah sah, batas atas sah, satu di bawah batas bawah → `ValueError`, satu di atas batas atas → `ValueError`, `True` → `TypeError`, `"5"` → `TypeError`, `None` → `TypeError`, dan untuk fungsi int: `3.0` → `TypeError`. Boleh ditulis sebagai satu test dengan tabel `subTest`, dan itu lebih disukai daripada 80 test kembar.

**Verifikasi Langkah 4:**

```bash
python3 -m unittest discover -s tests -t .
python3 -c "import gp2midi.play.validate as v; print(v.channel(9), v.key(127), v.gain(0.0))"
python3 -c "
import gp2midi.play.validate as v
for call in ('v.channel(16)', 'v.channel(True)', 'v.key(3.0)', 'v.velocity(-1)'):
    try: eval(call); print('TIDAK DITOLAK:', call)
    except (TypeError, ValueError) as e: print('ok', call, '->', e)
"
```

Harapan: test lolos; keempat panggilan rusak ditolak, tidak ada baris `TIDAK DITOLAK`.

---

## Langkah 5 — `gp2midi/play/audio.py`

Pembungkus tipis di atas pyfluidsynth. **Tidak ada logika musik di sini** — tidak tahu apa itu bar, tempo, atau timeline. Tugasnya tiga: pilih driver dan soundfont, validasi argumen sebelum menyeberang ke C, dan sediakan satu `now()` sebagai sumber jam.

**5a. Binding `remove_events` (fakta F-2).** Kode ini sudah diuji jalan; pakai apa adanya:

```python
import ctypes
import fluidsynth

# pyfluidsynth 1.4.0 tidak mem-bind fungsi ini, padahal ini satu-satunya cara
# membatalkan event yang sudah dijadwalkan. type = -1 berarti semua jenis event.
_remove_events = fluidsynth.cfunc(
    "fluid_sequencer_remove_events", None,
    ("seq", ctypes.c_void_p, 1),
    ("source", ctypes.c_short, 1),
    ("dest", ctypes.c_short, 1),
    ("type", ctypes.c_int, 1),
)
```

**5b. Pemilihan driver (fakta F-3).**

```python
def default_drivers() -> tuple[str, ...]:
    """Kandidat driver menurut platform, urut dari yang paling disukai."""
    if sys.platform == "darwin":
        return ("coreaudio",)
    if sys.platform.startswith("linux"):
        return ("pulseaudio", "alsa")
    return ()
```

`Audio` mencoba kandidat berurutan; yang pertama berhasil dipakai, dan nama yang dipakai disimpan di `self.driver`. Kalau semua gagal, `AudioError` dengan pesan yang menyebut semua yang dicoba beserta alasan masing-masing. Peringatan `Failed to set thread to high priority` di stderr **bukan** kegagalan — jangan coba menangkapnya.

**5c. Soundfont (fakta F-6).**

```python
SOUNDFONT_CANDIDATES = (
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/default.sf2",
)
```

`find_soundfont(explicit=None)` → kalau `explicit` diberi dan tidak ada filenya, `FileNotFoundError` yang menyebut path itu. Kalau tidak diberi, kandidat pertama yang ada. Kalau tak satu pun ada, `AudioError` yang menyebut flag `--soundfont`.

**5d. Kelas `Audio`:**

```python
class AudioError(RuntimeError):
    pass


class Audio:
    """Pembungkus Synth + Sequencer. Satu-satunya tempat yang menyentuh ctypes."""

    def __init__(self, soundfont: str | None = None, gain: float = 0.5,
                 samplerate: int = 44100, driver: str | None = None,
                 realtime: bool = True) -> None:
        ...

    # --- jam
    def now(self) -> int:
        """Waktu sequencer dalam ms. Satu-satunya sumber waktu untuk scheduler.
        realtime=True: timer sistem FluidSynth (fakta F-4).
        realtime=False: disiapkan untuk render offline F4; process() dipanggil manual."""

    # --- instrumen
    def select_program(self, channel: int, program: int, bank: int = 0,
                       drums: bool = False) -> None:
        """Drum -> bank 128, melodis -> bank yang diminta.
        Kalau program_select mengembalikan FLUID_FAILED, coba bank 0, lalu program 0.
        Fakta F-5: channel tanpa program_select itu senyap, jadi kegagalan di sini
        tidak boleh dilewatkan diam-diam -- catat ke self.warnings."""

    def cc(self, channel: int, controller: int, value: int) -> None: ...

    # --- penjadwalan (waktu absolut, ms)
    def note_on(self, at_ms: int, channel: int, key: int, velocity: int) -> None: ...
    def note_off(self, at_ms: int, channel: int, key: int) -> None: ...

    # --- pembatalan
    def clear_scheduled(self) -> None:
        """Buang seluruh event terjadwal lewat _remove_events."""
    def all_notes_off(self) -> None:
        """all_notes_off untuk channel 0-15. Dipakai setelah clear_scheduled,
        karena membatalkan event tidak mematikan not yang sudah berbunyi."""
    def panic(self) -> None:
        """clear_scheduled lalu all_notes_off, dalam urutan itu."""

    # --- umur objek
    def close(self) -> None:
        """Idempoten. Urutannya: panic, delete sequencer, delete synth."""
    def __enter__ / __exit__
```

Aturan implementasi yang tidak boleh ditawar:

1. **Setiap argumen lewat `gp2midi.play.validate` sebelum menyeberang ke C.** Tidak ada pengecualian "ini kan dari kode kita sendiri" — R2 tidak peduli dari mana nilainya datang.
2. `Sequencer(time_scale=1000, use_system_timer=realtime)` (K2, F-4). Simpan `self._dest = self._seq.register_fluidsynth(self._synth)` dan **selalu** teruskan `dest=self._dest` di setiap `note_on`/`note_off`.
3. `close()` harus aman dipanggil dua kali dan aman dipanggil setelah `__init__` gagal separuh jalan. Tulis `__init__` supaya atribut `self._synth = None` dan `self._seq = None` di-set paling awal.
4. `drums=True` → bank 128 (fakta F-5), tanpa kecuali, bahkan kalau `track.bank_msb` bilang lain.
5. `self.warnings: list[str]` berisi kegagalan non-fatal: `program_select` gagal, fallback bank dipakai, driver kandidat ditolak. CLI mencetaknya di akhir.

**File baru `tests/test_audio.py`.** Modul ini butuh fluidsynth, jadi di atasnya:

```python
import importlib.util
import unittest

HAS_FLUID = importlib.util.find_spec("fluidsynth") is not None


@unittest.skipUnless(HAS_FLUID, "butuh pyfluidsynth (.venv-app)")
class TestAudio(unittest.TestCase):
    ...
```

Empat test, semuanya **offline** (`realtime=False`, `gain=0.0`) supaya tidak berbunyi dan tidak butuh kartu suara:

1. `test_open_and_close` — buka, `close()` dua kali, tidak ada exception.
2. `test_validation_rejects_before_c` — `note_on(0, 16, 60, 100)` → `ValueError`; `note_on(0, 0, 60, 200)` → `ValueError`; `note_on(-1, 0, 60, 100)` → `ValueError`. Kalau salah satu malah membuat proses mati, validasinya tidak jalan.
3. `test_drum_bank_128` — `select_program(9, 0, drums=True)` tidak menambah apa pun ke `warnings`, dan not drum menghasilkan sampel tidak nol (render manual, bandingkan dengan fakta F-5 — ambang yang aman: puncak > 100).
4. `test_clear_scheduled_is_safe` — jadwalkan not jauh di depan, `panic()`, tidak crash, `now()` masih bisa dibaca.

**Verifikasi Langkah 5:**

```bash
python3 -m unittest discover -s tests -t .                  # test audio ter-skip, sisanya lolos
.venv-app/bin/python -m unittest discover -s tests -t .     # test audio ikut jalan
```

Harapan: baris pertama melaporkan sejumlah `skipped`; baris kedua `OK` tanpa skip untuk `TestAudio`. Peringatan `Failed to set thread to high priority` boleh muncul.

---

## Langkah 6 — `gp2midi/play/scheduler.py`

Thread lookahead dan transport. **Di sini tidak ada ctypes dan tidak ada parsing** — hanya `Timeline` di satu sisi dan `Audio` di sisi lain.

**6a. Konstanta dan laporan:**

```python
LOOKAHEAD_MS = 300      # PRD F2
FILL_INTERVAL_MS = 100  # sepertiga lookahead; thread harus bangun 3x sebelum jendela habis


@dataclass
class Report:
    """Angka untuk kriteria selesai F2. Semua dalam ms."""
    expected_ms: float      # durasi menurut TempoMap, dari posisi mulai
    actual_ms: float        # wall clock, time.monotonic
    drift_ms: float         # actual - expected
    late_events: int        # not yang dijadwalkan padahal waktunya sudah lewat
    max_fill_lag_ms: float  # keterlambatan terbesar bangunnya thread pengisi
    notes_scheduled: int
    def ok(self, tolerance_ms: float = 50.0) -> bool:
        return abs(self.drift_ms) <= tolerance_ms and self.late_events == 0
```

`late_events > 0` berarti thread pengisi kalah cepat dari playhead — not itu akan terdengar terlambat atau tertelan. Itu proxy terukur untuk "tanpa xrun/putus" di kriteria PRD; sisanya hanya bisa dipastikan dengan mendengar.

**6b. Kelas `Player`:**

```python
STOPPED, PLAYING, PAUSED = "stopped", "playing", "paused"


class Player:
    def __init__(self, timeline: Timeline, audio: Audio,
                 lookahead_ms: int = LOOKAHEAD_MS) -> None: ...

    def setup_instruments(self) -> None:
        """Untuk tiap track: select_program(channel, program, bank, drums=is_drums),
        lalu cc 7 = round(volume*127) dan cc 10 = round(pan*127).
        Dipanggil sekali sebelum play(). Fakta F-5: tanpa ini channel senyap."""

    def play(self, from_tick: int = 0) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...
    def seek(self, tick: int) -> None: ...
    def wait(self, timeout: float | None = None) -> Report:
        """Blok sampai lagu habis, stop(), atau timeout. Mengembalikan Report."""

    @property
    def state(self) -> str: ...
    @property
    def position_ms(self) -> float: ...
    @property
    def position_tick(self) -> int: ...
```

**6c. Aritmetika epoch — tulis persis seperti ini, ini sumber bug drift:**

Satu field `self._epoch` bertipe float, satuannya ms pada jam `audio.now()`:

```
_epoch = audio.now() - position_ms_saat_mulai
```

Dari situ semuanya turunan:

```
posisi sekarang (ms lagu)      = audio.now() - _epoch
waktu absolut not pada tick t  = _epoch + timeline.tempo.ms(t)
```

- `play(from_tick)`: `self._position_ms = tempo.ms(from_tick)`, `self._epoch = audio.now() - self._position_ms`, `self._cursor` = indeks not pertama yang `start >= from_tick` (pakai `bisect` pada daftar start, jangan scan linear), state `PLAYING`, start thread.
- `pause()`: catat `self._position_ms = audio.now() - self._epoch`, `audio.panic()`, state `PAUSED`. Thread **tidak** dimatikan; ia hanya berhenti mengisi.
- `resume()`: `self._epoch = audio.now() - self._position_ms`, `self._cursor` dihitung ulang dari `self._position_ms` (not yang sudah lewat jangan dijadwalkan ulang), state `PLAYING`.
- `stop()`: `audio.panic()`, state `STOPPED`, `self._position_ms = 0.0`, `self._cursor = 0`, bangunkan `wait()`.
- `seek(tick)`: `audio.panic()`, set `_position_ms` dan `_cursor` dari tick itu, lalu kalau sedang `PLAYING` set ulang `_epoch`. Seek saat `PAUSED` tidak memulai playback.

Jam sequencer **terus berjalan** saat paused — itu sebabnya posisi disimpan sebagai `_position_ms` dan `_epoch` selalu dihitung ulang saat resume. Jangan pernah menyimpan "tick mulai" saja.

**6d. Thread pengisi:**

```
def _loop(self):
    last_now = self._audio.now()
    while not self._quit.is_set():
        if self._state == PLAYING:
            now = self._audio.now()
            lag = (now - last_now) - FILL_INTERVAL_MS
            self._max_fill_lag = max(self._max_fill_lag, lag)
            last_now = now
            self._fill(now)
            if self._finished(now):
                ...  # catat actual_ms, state = STOPPED, set event selesai
        self._quit.wait(FILL_INTERVAL_MS / 1000.0)
```

`_fill(now)`:

```
horizon = (now - self._epoch) + self._lookahead_ms      # dalam ms lagu
notes = self._timeline.notes
while self._cursor < len(notes):
    note = notes[self._cursor]
    on_ms = tempo.ms(note.start)
    if on_ms > horizon:
        break
    at_on = self._epoch + on_ms
    if at_on < now:
        self._late += 1
        at_on = now
    at_off = max(round(self._epoch + tempo.ms(note.end)), round(at_on) + 1)
    self._audio.note_on(round(at_on), note.channel, note.pitch, note.velocity)
    self._audio.note_off(at_off, note.channel, note.pitch)
    self._cursor += 1
    self._scheduled += 1
```

Dua hal yang sering salah di blok itu:

- **`at_off` wajib lebih besar dari `at_on`.** Dua not sama pada pitch dan channel yang sama bisa jatuh di ms yang sama setelah pembulatan; kalau note-off-nya tidak digeser minimal 1 ms, FluidSynth memainkan satu not lalu mematikannya dengan note-off milik not sebelumnya. Ini padanan dari `ORDER_*` di SMF writer, tapi di sequencer **tidak ada yang mengurusnya untukmu**.
- **Perbandingan selalu di satu ruang waktu.** `on_ms` dan `horizon` di ruang "ms lagu"; `at_on`, `at_off`, `now` di ruang "ms sequencer". Mencampur keduanya menghasilkan drift yang baru kelihatan setelah beberapa menit.

`_finished(now)`: `self._cursor >= len(notes)` **dan** `(now - self._epoch) >= timeline.duration_ms`. Pakai `duration_ms` (= `last_note_end`), bukan `end_tick` — fakta F-8.

**6e. Batas waktu opsional.** `play(from_tick, limit_ms=None)`: kalau `limit_ms` diberi, `_finished` juga benar ketika `(now - self._epoch) - position_awal >= limit_ms`. Ini yang dipakai `--seconds` di CLI dan `verify.sh`, supaya verifikasi harian tidak perlu 4 menit.

**File baru `tests/test_scheduler.py`**, pola `skipUnless` sama seperti `test_audio.py`. Empat test, semua `gain=0.0`:

1. `test_short_excerpt_drift` — fixture atau 10 detik pertama korpus, `limit_ms=5000`. `abs(report.drift_ms) <= 50` dan `report.late_events == 0`.
2. `test_pause_resume_no_stuck_notes` — play, tunggu 1 detik, `pause()`, pastikan `state == PAUSED` dan `position_ms` berhenti naik (baca dua kali, jeda 300 ms), `resume()`, pastikan naik lagi. Tidak crash, tidak hang.
3. `test_from_bar_starts_later` — `play(from_tick=timeline.bar_tick(5))`, `position_tick` di awal sudah `>= bar_tick(5)`, dan not pertama yang dijadwalkan bukan not pertama lagu.
4. `test_stop_is_idempotent` — `stop()` dua kali tanpa `play()` sebelumnya, dan `stop()` dua kali setelah `play()`. Tidak ada exception, thread benar-benar mati (`thread.is_alive()` False setelah `close()`).

**Verifikasi Langkah 6:**

```bash
.venv-app/bin/python -m unittest discover -s tests -t . 2>&1 | tail -5
```

Harapan: `OK`. Kalau sebuah test hang, kemungkinan besar `wait()` tidak pernah selesai karena `_finished` memakai `end_tick` — lihat fakta F-8.

---

## Langkah 7 — Subcommand `play` di CLI `gp2midi`

**File baru `gp2midi/play/cli.py`** berisi satu fungsi `run(args) -> int`. Tidak ada `argparse` di dalamnya dan tidak ada `__main__.py` baru: parser-nya ada di `gp2midi/cli.py` yang sudah ada, karena argparse itu stdlib dan harus tetap bisa mencetak `--help` di mesin tanpa FluidSynth.

**Di `gp2midi/cli.py`**, tambahkan subparser `play` (pakai `parents=[common]`, jadi ia ikut dapat `input` dan `--no-expand-repeats`) dan `_cmd_play` dengan import lazy seperti di Keputusan 3. Tempatkan subparser `play` **setelah** `convert` dan sebelum `check`.

Argumen subcommand `play`:

```
python3 -m gp2midi play FILE [opsi]

  --from BAR          mulai dari bar ke-BAR (1-based, urutan playback; default 1)
  --seconds N         berhenti setelah N detik playback (default: sampai habis)
  --soundfont PATH    file .sf2 (default: kandidat sistem, lihat --help)
  --driver NAME       paksa driver audio tertentu
  --gain G            0.0-10.0 (default 0.5)
  --silent            gain 0.0; driver tetap dibuka dan jam tetap nyata, jadi
                      pengukuran drift tetap sah tanpa mengeluarkan suara
  --report            cetak Report di akhir; exit 1 kalau drift > 50 ms atau late_events > 0
  --gate G            diteruskan ke Options
  --no-expand-repeats diteruskan ke Options
```

Perilaku:

1. `parse(FILE)` → `build_timeline` → cetak satu baris ringkas: judul, jumlah bar, jumlah not, durasi `mm:ss`.
2. `Audio(...)` → `Player(...)` → `setup_instruments()` → `play(from_tick)`.
3. `Ctrl-C` (`KeyboardInterrupt`) harus **berhenti bersih**: `player.stop()`, `audio.close()`, exit 130. Not nyangkut setelah Ctrl-C adalah bug, bukan hal yang bisa dimaklumi.
4. `audio.warnings` dicetak ke stderr di akhir, satu baris per peringatan.
5. Error yang sudah diantisipasi (file tidak ada, soundfont tidak ada, semua driver gagal, `--from` di luar rentang) dicetak sebagai `gp2midi: <pesan>` ke stderr dengan exit 2 — pola yang sama dengan `gp2midi/cli.py`. Jangan biarkan traceback bocor ke pengguna untuk kasus-kasus ini.
6. Dengan `--report`, format outputnya stabil dan mudah dibaca mesin, contoh:
   ```
   expected 254742.9 ms  actual 254761.2 ms  drift +18.3 ms  late 0  max_fill_lag 7.4 ms  notes 3975
   ```

**Di `pyproject.toml`:** tambahkan `"gp2midi.play"` ke `[tool.setuptools] packages` (jadi `["gp2midi", "gp2midi.play"]`) dan tambahkan

```toml
[project.optional-dependencies]
play = ["pyfluidsynth==1.4.0", "numpy"]
```

`dependencies` di `[project]` tetap `[]` dan `[project.scripts]` tetap hanya `gp2midi`. Jadi `pip install gp2midi` tetap tanpa dependensi, `pip install "gp2midi[play]"` yang membawa FluidSynth.

**Verifikasi Langkah 7:**

```bash
.venv-app/bin/python -m gp2midi play --help
.venv-app/bin/python -m gp2midi play "media/seventeen-Menemukanmu-05-16-2026.gp" --silent --seconds 20 --report
.venv-app/bin/python -m gp2midi play "media/seventeen-Menemukanmu-05-16-2026.gp" --silent --seconds 10 --from 33 --report
.venv-app/bin/python -m gp2midi play /tidak/ada.gp ; echo "exit=$?"

# yang ini pakai python3 sistem, yang TIDAK punya fluidsynth:
python3 -m gp2midi --help                     # harus memuat, dan menampilkan subcommand play
python3 -m gp2midi play --help                # harus memuat juga: parser itu stdlib
python3 -m gp2midi convert media/*.gp -o /tmp/tanpa-fluid.mid   # harus exit 0
python3 -m gp2midi play media/*.gp ; echo "exit=$?"
```

Harapan: dua run `--silent` mencetak `drift` di bawah 50 ms dan `late 0`, exit 0; `/tidak/ada.gp` mencetak `gp2midi: ...` dan `exit=2` tanpa traceback.

Empat baris terakhir adalah inti Keputusan 1 dan 3: tiga yang pertama **wajib berhasil** tanpa FluidSynth terpasang, dan yang terakhir wajib gagal dengan pesan yang bisa ditindaklanjuti — `gp2midi: playback butuh FluidSynth; pasang dengan pip install "gp2midi[play]"` dan exit 2, **bukan** `ModuleNotFoundError`. Artinya `_cmd_play` menangkap `ImportError` dari import lazy itu.

---

## Langkah 8 — `tools/verify.sh` tingkat 4

Tambahkan bagian baru **setelah** bagian `3/3`, dan ubah label `1/3`, `2/3`, `3/3` menjadi `1/4`, `2/4`, `3/4`.

```bash
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
```

Dua alasan bentuknya begini: unit test dijalankan **dua kali** (sekali dengan `python3` sistem supaya test engine tetap bebas dependensi, sekali dengan `.venv-app` supaya test audio dan scheduler benar-benar jalan, bukan ter-skip selamanya); dan verifikasi harian tidak boleh memakan 4 menit, sementara kriteria selesai F2 tetap bisa diuji penuh dengan satu env var.

**Verifikasi Langkah 8 — ini gerbang kriteria selesai:**

```bash
./tools/verify.sh                        # harapan: SEMUA LOLOS, 4 bagian
VERIFY_PLAYBACK=1 ./tools/verify.sh      # ~4.5 menit; harapan: SEMUA LOLOS
```

Di run kedua, baris report harus menunjukkan `expected` sekitar `254742.9` ms, `drift` dalam ±50 ms, dan `late 0`.

---

## Langkah 9 — Dokumentasi

**9a. `AGENTS.md`.** Bagian `## Constraint` **sudah diperbarui pemilik project pada 2026-10-27** — tiga jebakan playback (channel bisu tanpa `program_select`, antrian sequencer yang tidak bisa dibatalkan, `ORDER_*` yang tidak berlaku di jalur playback) dan batas dependensi `gp2midi/play/` sudah ada di sana. **Baca ketiganya sebelum Langkah 5 dan 6, jangan tulis ulang, jangan parafrase.**

Yang masih perlu kamu ubah di `AGENTS.md` hanya dua kalimat, dan baru setelah Langkah 8 benar-benar jalan:

- Bagian `## Verifikasi`: "Tiga tingkat" jadi empat, dan sebutkan tingkat keempat beserta `VERIFY_PLAYBACK=1` untuk uji drift lagu penuh.
- Butir "Engine core nol dependensi": tambahkan satu kalimat bahwa batas itu dijaga `tests/test_no_native_deps.py`. Kalimat itu baru boleh ditulis **setelah** test-nya ada dan lolos — jangan menjanjikan file yang belum ada.

**9b. `README.md`.** Tambahkan bagian baru `## Playback` setelah `## Pemakaian`: cara membuat `.venv-app`, contoh `play`, tabel opsi, dan satu kalimat bahwa engine tetap nol dependensi sementara playback butuh FluidSynth. Perbarui juga paragraf pembuka kalau ia masih mengklaim repo ini cuma konverter.

**9c. Jangan sentuh `PRD.md`.** Kalau kamu menemukan sesuatu yang layak masuk §7 (misalnya status deprecated timer sistem di fakta F-4), atau §8 yang butir "nama paket"-nya sudah terjawab, tulis itu di laporan akhirmu sebagai usulan untuk pemilik project, jangan edit sendiri.

**Verifikasi Langkah 9:** baca ulang `README.md` dan jalankan setiap perintah yang kamu tulis di sana. Perintah di dokumentasi yang tidak pernah dijalankan adalah dokumentasi yang salah.

---

## Yang tidak disentuh di fase ini

- `gp2midi/gpif.py`, `gp2midi/model.py`, `gp2midi/container.py`, `gp2midi/smf.py` — F2 tidak menyentuh parsing maupun penulisan SMF.
- `gp2midi/cli.py` — **hanya** boleh bertambah: subparser `play` dan `_cmd_play` (Langkah 7). `_cmd_info`, `_cmd_convert`, `_cmd_check`, dan parser `common` tidak berubah; kalau re-export di Langkah 2a terasa kurang, tambah re-export di `convert.py`, jangan ubah import di `cli.py`.
- Perilaku `to_midi`, `to_midi_merged`, `to_midi_per_track` — wajib byte-identik (Langkah 0c).
- `PPQ = 960` dan `time_scale = 1000`.
- **Transpose, tempo multiplier, mute/solo, volume realtime, metronom.** Semua itu F3. `Player` di fase ini hanya memainkan apa adanya. Menambahkannya sekarang akan membuat kriteria drift tidak terbukti, karena bug timing dan bug parameter jadi tercampur.
- **Export MP3/WAV.** F4. `Audio(realtime=False)` disiapkan untuk itu, tapi jangan ada loop render di fase ini.
- GUI apa pun.
- `PRD.md`.

## Kalau macet

Berhenti dan laporkan, jangan menebak, pada salah satu dari ini:

- Satu saja hash di `cek-baseline` tidak cocok setelah Langkah 2. Refactor timeline wajib byte-identik; ketidakcocokan berarti ada perubahan perilaku yang tak disengaja, bukan sesuatu yang bisa diakali dengan memperbarui baseline.
- `python3 -m unittest` turun dari 34 test lolos, kapan pun.
- Proses mati tanpa traceback (segfault). Itu R2: ada argumen yang menyeberang ke C tanpa divalidasi. Laporkan panggilan terakhir yang kamu tambahkan, jangan coba-coba memperbaiki dengan mengubah nilai.
- `drift_ms` di atas 50 ms atau `late_events > 0` pada cuplikan 20 detik. Laporkan `Report` lengkapnya beserta `max_fill_lag_ms`; jangan "perbaiki" dengan memperbesar toleransi atau lookahead sebelum tahu sebabnya.
- `.venv-app/bin/python -m unittest` hang. Laporkan test mana; hampir selalu `wait()` yang tidak pernah selesai.
- Semua kandidat driver audio gagal dibuka. Laporkan pesan masing-masing; di mesin ini pulseaudio dan alsa dua-duanya terbukti jalan (fakta F-3), jadi kegagalan berarti ada yang berubah di lingkungan.

Laporkan apa yang dijalankan, output lengkapnya, dan di langkah mana.

## Yang harus ada di laporan akhirmu

- Hasil `./tools/verify.sh` dan `VERIFY_PLAYBACK=1 ./tools/verify.sh`, apa adanya.
- Baris `--report` untuk lagu penuh: expected, actual, drift, late, max_fill_lag.
- Jumlah test sebelum dan sesudah.
- Pernyataan eksplisit bahwa **kualitas suara belum diverifikasi** karena kamu tidak bisa mendengar, beserta perintah yang perlu dijalankan pemilik project:
  ```bash
  .venv-app/bin/python -m gp2midi play "media/seventeen-Menemukanmu-05-16-2026.gp"
  ```
- Usulan untuk `PRD.md` kalau ada — misalnya §7 risiko baru (status deprecated timer sistem, fakta F-4), atau §8 butir "nama paket" yang kini sudah terjawab dan bisa dihapus dari daftar keputusan terbuka.
