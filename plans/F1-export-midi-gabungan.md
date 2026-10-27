# F1 — Export MIDI gabungan (SMF type 0)

Fase pertama di `PRD.md` §6. Estimasi 0.5 hari. Tanpa dependensi baru.

## Baca dulu

1. `AGENTS.md` — seluruhnya. Pendek.
2. `PRD.md` keputusan **K7** — alasan "1 track gabungan" berarti satu MTrk dengan channel tetap terpisah, bukan satu channel.

Dua constraint dari AGENTS.md yang kena di fase ini:

- **Drum bukan pitch.** Track drum harus tetap mendarat di channel 10. `_assign_channels()` sudah mengurusnya — pakai fungsi itu, jangan hitung channel sendiri.
- **Note-off mendahului note-on pada tick yang sama.** Dijamin oleh `MidiTrack.ORDER_*`. Kamu tidak perlu menyentuh urutan event; cukup pakai `midi.note_on()` / `midi.note_off()` seperti yang sudah ada.

## Hasil akhir

Perintah baru `convert --merge` menghasilkan satu file SMF **type 0**: satu MTrk berisi seluruh event dari semua track, channel per instrumen dipertahankan, plus tempo/time signature/key signature.

Selesai ketika keempat hal ini benar:

1. `tools/verify.sh` lolos (termasuk pengecekan file merged yang kamu tambahkan di Langkah 6).
2. mido membaca hasilnya sebagai `type 0` dengan tepat 1 track.
3. Jumlah not di file merged **sama persis** dengan total not dari `convert` biasa.
4. Nol not menggantung — `tools/verify_midi.py` yang memutuskan.

---

## Langkah 1 — Pisahkan setup channel dari nama track

**Masalahnya:** `_write_setup()` di `gp2midi/convert.py` memancarkan `track_name`. Di SMF type 0 hanya ada satu MTrk, jadi memanggilnya untuk 5 track akan menumpuk 5 meta nama di satu track. Yang dibutuhkan di mode merged hanya bagian bank/program/volume/pan.

**Di `gp2midi/convert.py`**, ganti fungsi `_write_setup` yang sekarang dengan dua fungsi ini:

```python
def _write_channel_setup(midi: MidiTrack, track: Track, channel: int) -> None:
    """Bank, program, volume, pan. Tanpa nama track, supaya aman dipakai di SMF type 0."""
    if track.bank_msb or track.bank_lsb:
        midi.control_change(0, channel, 0, track.bank_msb)
        midi.control_change(0, channel, 32, track.bank_lsb)
    midi.program_change(0, channel, 0 if track.is_drums else track.program)
    midi.control_change(0, channel, 7, max(0, min(127, round(track.volume * 127))))
    midi.control_change(0, channel, 10, max(0, min(127, round(track.pan * 127))))


def _write_setup(midi: MidiTrack, track: Track, channel: int) -> None:
    midi.track_name(track.name or f"Track {track.index + 1}")
    _write_channel_setup(midi, track, channel)
```

Pemanggil `_write_setup` yang lain (di `to_midi` dan `to_midi_per_track`) **tidak diubah**.

**Jalankan, dan jangan lanjut sebelum lolos:**

```
./tools/verify.sh
```

Harapan: `Ran 29 tests ... OK` dan `SEMUA LOLOS`. Langkah ini murni refactor — output byte-nya harus identik dengan sebelumnya. Kalau ada test gagal, berarti refactor-nya salah; perbaiki dulu di sini.

---

## Langkah 2 — Tambah `to_midi_merged()`

**Di `gp2midi/convert.py`**, tambahkan fungsi baru **setelah** `to_midi()` dan sebelum `to_midi_per_track()`.

Spesifikasinya, ikuti urutan ini:

```python
def to_midi_merged(score: Score, out_path: str | Path, options: Options | None = None) -> dict:
    """Tulis satu SMF type 0: semua track digabung ke satu MTrk, channel tetap terpisah."""
```

1. `options = options or Options()`
2. `order = playback_order(score, options.expand_repeats)`
3. `starts, end_tick = _bar_starts(score, order)`
4. `channels = _assign_channels(score.tracks)`
5. `midi = _conductor(score, order, starts, end_tick)` — **pakai ulang `_conductor`**. Ia sudah memasang nama (judul lagu), tempo, time signature, key signature, dan marker, dan ia memanggil `track_name` tepat sekali. Itu satu-satunya nama track di file ini.
6. Untuk setiap `track` di `score.tracks`, urut:
   - `notes = _track_notes(track, order, starts, options)`
   - kalau `notes` kosong dan `options.include_empty` False → catat di summary sebagai `written: False`, lalu `continue`
   - `channel = channels[track.index]`
   - kalau `channel` sudah dipakai track lain → catat ke daftar `collisions` berisi `(nama track ini, nama track sebelumnya, channel + 1)`
   - `_write_channel_setup(midi, track, channel)`
   - `_emit(midi, notes, channel)`
   - catat di summary: `{"track": ..., "notes": len(notes), "channel": channel + 1, "written": True}`
7. `write_file(out_path, [midi], score.ppq)` — **daftar berisi satu elemen**. `write_file` otomatis menulis type 0 kalau jumlah track tepat 1; kamu tidak perlu mengatur format apa pun.
8. Kembalikan dict dengan kunci: `path`, `format` (nilai `0`), `ppq`, `bars_played`, `end_tick`, `tracks` (summary), `collisions`.

Catatan soal `collisions`: dua track bisa berbagi channel kalau ada lebih dari 15 track melodis, atau ada dua track drum (keduanya dipaksa ke channel 10). Di file korpus hal ini tidak terjadi, tapi tetap dilaporkan karena di satu MTrk tabrakan channel berarti program change saling menimpa.

---

## Langkah 3 — Ekspor dari paket

**Di `gp2midi/__init__.py`**, tambahkan `to_midi_merged` ke import dari `.convert` dan ke `__all__`.

---

## Langkah 4 — Tambah `--merge` ke CLI

**Di `gp2midi/cli.py`, fungsi `build_parser()`**, di blok subparser `convert`: `--split` dan `--merge` tidak boleh dipakai bersamaan, jadi pindahkan `--split` ke grup eksklusif bersama `--merge`:

```python
    mode = convert.add_mutually_exclusive_group()
    mode.add_argument("--split", action="store_true",
                      help="tulis satu file MIDI per track, bukan satu file multi-track")
    mode.add_argument("--merge", action="store_true",
                      help="tulis satu file MIDI type 0, semua track digabung jadi satu")
```

Argumen `--gate` dan `--include-empty` tetap di `convert`, **bukan** di grup itu.

**Di fungsi `_cmd_convert()`**, tambahkan cabang `args.merge` **sebelum** cabang `args.split`. Nama file default sama dengan mode biasa: `Path(args.input).with_suffix(".mid")`. Cetak ringkasannya dengan pola yang sama seperti cabang biasa, lalu untuk setiap item di `result["collisions"]` cetak peringatan ke `sys.stderr`:

```python
        for name, other, channel in result["collisions"]:
            print(f"gp2midi: {name} berbagi channel {channel} dengan {other}", file=sys.stderr)
```

Perbarui juga teks `help` untuk `-o/--output` supaya menyebut mode merge.

---

## Langkah 5 — Test

**Di `tests/test_gp2midi.py`**, tambahkan class `TestMerged(unittest.TestCase)` dengan `setUp` yang sama seperti `TestConvert` (`parse_fixture()` + `tempfile.mkdtemp()`).

Lima test, tulis semuanya:

1. **`test_type_zero_single_track`** — panggil `convert.to_midi_merged(self.score, self.out / "m.mid")`, baca header dan pastikan `(fmt, ntrk) == (0, 1)`. Pola `struct.unpack(">IHHH", raw[4:14])` sudah dipakai di `TestConvert.test_multitrack_file` — ikuti itu.

2. **`test_exactly_one_track_name`** — ini test untuk jebakan di Langkah 1. Meta track name adalah `FF 03`:
   ```python
   raw = (self.out / "m.mid").read_bytes()
   self.assertEqual(raw.count(b"\xff\x03"), 1)
   ```

3. **`test_channels_preserved`** — fixture punya Gitar (channel 1) dan Drum (channel 10). Pastikan `[t["channel"] for t in result["tracks"]] == [1, 10]`, dan byte status untuk kedua channel hadir: `b"\x90"` (note-on ch 1) dan `b"\x99"` (note-on ch 10).

4. **`test_note_count_matches_multitrack`** — tulis file lewat `to_midi` dan lewat `to_midi_merged`, lalu pastikan total `notes` dari kedua summary sama.

5. **`test_tempo_and_timesig_present`** — pastikan `b"\xff\x51"` (set tempo) dan `b"\xff\x58"` (time signature) ada di byte hasil.

**Jalankan:**

```
python3 -m unittest discover -s tests -t .
```

Harapan: `Ran 34 tests ... OK`. Flag `-t .` wajib; tanpa itu muncul `ImportError: Start directory is not importable`.

---

## Langkah 6 — Masukkan file merged ke oracle

**Di `tools/verify.sh`**, di bagian `3/3`, di dalam loop yang sudah ada, tulis juga versi merged-nya supaya ikut diperiksa oracle setiap kali:

```bash
        python3 -m gp2midi convert "$file" --merge -o "$out/$(basename "$file").merged.mid" >/dev/null || status=1
```

`tools/verify_midi.py` sudah punya aturan "type 0 harus tepat 1 track", jadi tidak perlu diubah.

**Jalankan:**

```
./tools/verify.sh
```

Harapan: `SEMUA LOLOS`, dan sekarang ada 4 baris di bagian oracle — dua file biasa `type 1, 6 trk` dan dua file merged `type 0, 1 trk`. Jumlah not di baris merged harus sama dengan baris `type 1` dari file yang sama.

---

## Langkah 7 — README

**Di `README.md`:**

- Tambahkan contoh di blok "Pemakaian":
  ```bash
  python3 -m gp2midi convert "lagu.gp" --merge -o lagu.mid   # 1 file type 0, semua track digabung
  ```
- Tambahkan baris `--merge` ke tabel "Opsi convert".
- Di bagian "Yang diterjemahkan", pada poin **Track → MTrk**, sebutkan mode merge sebagai alternatif.

---

## Yang tidak disentuh di fase ini

Biarkan apa adanya; perubahan di sini bukan bagian dari F1:

- `gp2midi/gpif.py`, `gp2midi/model.py`, `gp2midi/container.py` — F1 tidak menyentuh parsing.
- `gp2midi/smf.py` — `write_file` sudah memilih type 0 sendiri untuk satu track.
- `to_midi()` dan `to_midi_per_track()` — perilakunya harus tetap identik. Test yang ada adalah jaring pengamannya.
- `PPQ = 960` di `gpif.py` — angka itu menanggung beban, lihat AGENTS.md.
- `PRD.md` dan `AGENTS.md`.

## Kalau macet

Berhenti dan laporkan, jangan menebak, pada salah satu dari ini:

- `tools/verify.sh` gagal di Langkah 1 — refactor tidak boleh mengubah perilaku apa pun, jadi kegagalan di situ berarti ada yang salah paham, bukan ada yang perlu diakali.
- Jumlah not merged tidak sama dengan jumlah not multi-track.
- `raw.count(b"\xff\x03")` bukan 1.

Laporkan apa yang dijalankan, output lengkapnya, dan di langkah mana.
