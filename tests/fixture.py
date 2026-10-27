"""Pembuat fixture GPIF minimal untuk pengujian."""

from __future__ import annotations

import zipfile
from pathlib import Path

GPIF_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<GPIF>
  <GPVersion>8.1.3</GPVersion>
  <Score>
    <Title><![CDATA[Fixture]]></Title>
    <Artist><![CDATA[Tester]]></Artist>
  </Score>
  <MasterTrack>
    <Tracks>0 1</Tracks>
    <Automations>
      <Automation>
        <Type>Tempo</Type>
        <Bar>0</Bar>
        <Position>0</Position>
        <Value>100 2</Value>
      </Automation>
    </Automations>
  </MasterTrack>
  <Tracks>
    <Track id="0">
      <Name>Gitar</Name>
      <ShortName>gtr</ShortName>
      <InstrumentSet><Type>electricGuitar</Type></InstrumentSet>
      <Sounds><Sound><MIDI><LSB>0</LSB><MSB>0</MSB><Program>30</Program></MIDI></Sound></Sounds>
      <RSE><ChannelStrip><Parameters>0.6 0.68 1 0.62 0.75 0.5 0.66 0.18 0.6 0 0.5 0.5 0.80 0.5 0.5 0.5</Parameters></ChannelStrip></RSE>
      <Staves><Staff><Properties>
        <Property name="Tuning"><Pitches>40 45 50 55 59 64</Pitches></Property>
      </Properties></Staff></Staves>
    </Track>
    <Track id="1">
      <Name>Drum</Name>
      <ShortName>drm</ShortName>
      <InstrumentSet><Type>drumKit</Type></InstrumentSet>
      <Sounds><Sound><MIDI><LSB>0</LSB><MSB>0</MSB><Program>0</Program></MIDI></Sound></Sounds>
    </Track>
  </Tracks>
  <MasterBars>
{master_bars}
  </MasterBars>
  <Bars>
{bars}
  </Bars>
  <Voices>
{voices}
  </Voices>
  <Beats>
{beats}
  </Beats>
  <Notes>
{notes}
  </Notes>
  <Rhythms>
{rhythms}
  </Rhythms>
</GPIF>
"""


def build_gpif(master_bars: str, bars: str, voices: str, beats: str, notes: str, rhythms: str) -> str:
    return GPIF_TEMPLATE.format(
        master_bars=master_bars, bars=bars, voices=voices,
        beats=beats, notes=notes, rhythms=rhythms,
    )


def write_gp(path: Path, gpif: str) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("VERSION", "7.0")
        zf.writestr("Content/score.gpif", gpif)
    return path


def simple_score() -> str:
    """Dua bar 4/4: bar 1 empat not quarter di gitar, bar 2 whole note di-tie."""
    master_bars = """
    <MasterBar>
      <Key><AccidentalCount>0</AccidentalCount><Mode>Major</Mode></Key>
      <Time>4/4</Time>
      <Bars>0 2</Bars>
    </MasterBar>
    <MasterBar>
      <Key><AccidentalCount>0</AccidentalCount><Mode>Major</Mode></Key>
      <Time>4/4</Time>
      <Bars>1 3</Bars>
    </MasterBar>"""
    bars = """
    <Bar id="0"><Clef>G2</Clef><Voices>0 -1 -1 -1</Voices></Bar>
    <Bar id="1"><Clef>G2</Clef><Voices>1 -1 -1 -1</Voices></Bar>
    <Bar id="2"><Clef>Neutral</Clef><Voices>2 -1 -1 -1</Voices></Bar>
    <Bar id="3"><Clef>Neutral</Clef><Voices>3 -1 -1 -1</Voices></Bar>"""
    voices = """
    <Voice id="0"><Beats>0 1 2 3</Beats></Voice>
    <Voice id="1"><Beats>4</Beats></Voice>
    <Voice id="2"><Beats>5 5 5 5</Beats></Voice>
    <Voice id="3"><Beats>6</Beats></Voice>"""
    beats = """
    <Beat id="0"><Rhythm ref="0"/><Dynamic>F</Dynamic><Notes>0</Notes></Beat>
    <Beat id="1"><Rhythm ref="0"/><Dynamic>F</Dynamic><Notes>1</Notes></Beat>
    <Beat id="2"><Rhythm ref="0"/><Dynamic>P</Dynamic><Notes>2</Notes></Beat>
    <Beat id="3"><Rhythm ref="0"/><Dynamic>F</Dynamic><Notes>3</Notes></Beat>
    <Beat id="4"><Rhythm ref="1"/><Dynamic>F</Dynamic><Notes>4</Notes></Beat>
    <Beat id="5"><Rhythm ref="0"/><Dynamic>F</Dynamic><Notes>5</Notes></Beat>
    <Beat id="6"><Rhythm ref="1"/><Dynamic>F</Dynamic></Beat>"""
    notes = """
    <Note id="0"><InstrumentArticulation>0</InstrumentArticulation><Properties>
      <Property name="Midi"><Number>64</Number></Property>
      <Property name="Fret"><Fret>0</Fret></Property>
      <Property name="String"><String>0</String></Property>
    </Properties></Note>
    <Note id="1"><InstrumentArticulation>0</InstrumentArticulation><Properties>
      <Property name="Midi"><Number>67</Number></Property>
    </Properties></Note>
    <Note id="2"><InstrumentArticulation>0</InstrumentArticulation><Properties>
      <Property name="Midi"><Number>69</Number></Property>
      <Property name="Muted"/>
    </Properties></Note>
    <Note id="3"><InstrumentArticulation>0</InstrumentArticulation>
      <Tie origin="true" destination="false"/>
      <Properties><Property name="Midi"><Number>71</Number></Property></Properties></Note>
    <Note id="4"><InstrumentArticulation>0</InstrumentArticulation>
      <Tie origin="false" destination="true"/>
      <Properties><Property name="Midi"><Number>71</Number></Property></Properties></Note>
    <Note id="5"><InstrumentArticulation>0</InstrumentArticulation><Properties>
      <Property name="Midi"><Number>42</Number></Property>
    </Properties></Note>"""
    rhythms = """
    <Rhythm id="0"><NoteValue>Quarter</NoteValue></Rhythm>
    <Rhythm id="1"><NoteValue>Whole</NoteValue></Rhythm>"""
    return build_gpif(master_bars, bars, voices, beats, notes, rhythms)
