"""Export the analyzed chords and beat grid as a Standard MIDI File."""

from bisect import bisect_right
from itertools import pairwise
from math import ceil
from pathlib import Path
from typing import NamedTuple

import mido
import mir_eval


class _Tempo(NamedTuple):
    seconds: float
    tick: int
    us_per_quarter: int


def _interval(seconds: float, ticks: int, ppq: int) -> tuple[int, int]:
    # A long gap may exceed MIDI's three-byte tempo limit. Give it whole extra pulses.
    duration = seconds * 1_000_000 * ppq
    ticks *= max(1, ceil(duration / (ticks * 0xFFFFFF)))
    return ticks, round(duration / ticks)


def _tempo_map(beats: list[float], bpm: float | None, pulse: int, ppq: int) -> list[_Tempo]:
    if len(beats) < 2:
        _, tempo = _interval(60 / (bpm or 120), pulse, ppq)
        return [_Tempo(0, 0, tempo)]

    points = []
    tick = 0
    if beats[0] > 0:
        # Preserve the lead-in in seconds and put the first detected beat on a MIDI beat.
        lead_pulses = max(1, round(beats[0] / (beats[1] - beats[0])))
        tick, tempo = _interval(beats[0], lead_pulses * pulse, ppq)
        points.append(_Tempo(0, 0, tempo))
    for start, end in pairwise(beats):
        ticks, tempo = _interval(end - start, pulse, ppq)
        points.append(_Tempo(start, tick, tempo))
        tick += ticks
    return points


def _tick_at(seconds: float, tempos: list[_Tempo], ppq: int) -> int:
    point = tempos[bisect_right(tempos, seconds, key=lambda p: p.seconds) - 1]
    return point.tick + mido.second2tick(seconds - point.seconds, ppq, point.us_per_quarter)


def write_midi(report: dict, path: Path) -> None:
    """Write a conductor track and a block-chord track at the report's original times."""
    midi = mido.MidiFile(type=1, ticks_per_beat=960)
    conductor = midi.add_track("Beat grid")
    ppq = midi.ticks_per_beat
    pulse = ppq
    meter = report["meter"]
    if counted := meter["beats_per_bar"]:
        signature = meter.get("time_signature") or f"{counted}/4"
        numerator, denominator = map(int, signature.split("/"))
        conductor.append(mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator))
        # A pulse in 6/8 can be a dotted quarter (two per bar) or an eighth (six per bar).
        pulse = round(ppq * 4 * numerator / (denominator * counted))
    tempos = _tempo_map(report["beats"], report["tempo"]["bpm"], pulse, ppq)
    last_tick = 0
    for point in tempos:
        conductor.append(
            mido.MetaMessage("set_tempo", tempo=point.us_per_quarter, time=point.tick - last_tick)
        )
        last_tick = point.tick
    end_tick = _tick_at(report["file"]["duration"], tempos, ppq)
    conductor.append(mido.MetaMessage("end_of_track", time=max(0, end_tick - last_tick)))

    chords = midi.add_track("Chords")
    last_tick = 0
    for segment in report["chords"]["segments"]:
        if not segment["is_chord"]:
            continue
        start, end = (_tick_at(segment[key], tempos, ppq) for key in ("start", "end"))
        if end <= start:
            continue
        root, bitmap, bass = mir_eval.chord.encode(segment["label"], reduce_extended_chords=True)
        # Voice each pitch class once, above the indicated bass for slash chords.
        lowest = 48 + (root + bass) % 12
        notes = sorted({lowest, *(lowest + (int(i) - bass) % 12 for i in bitmap.nonzero()[0])})
        for kind, tick in (("note_on", start), ("note_off", end)):
            for note in notes:
                chords.append(mido.Message(kind, note=note, time=tick - last_tick))
                last_tick = tick
    midi.save(path)
