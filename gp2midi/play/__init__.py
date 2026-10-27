"""Subpaket lapisan aplikasi: playback, audio, dan pemutar.

Satu-satunya tempat di mana dependensi native (pyfluidsynth, numpy)
dibolehkan. Modul di `gp2midi/*.py` tetap stdlib murni; batas ini dijaga
`tests/test_no_native_deps.py`.
"""
