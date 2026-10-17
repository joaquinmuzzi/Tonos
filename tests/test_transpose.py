"""The page's transposition (tonos/web/transpose.js) spells keys and chords like notation.py."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tonos.analysis.notation import Speller, describe_chord, key_name, scale_names

SCRIPT = Path(__file__).parent.parent / "tonos" / "web" / "transpose.js"
ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
QUALITIES = [
    "maj",
    "min",
    "7",
    "maj7",
    "min7",
    "dim",
    "dim7",
    "hdim7",
    "aug",
    "sus4",
    "sus2",
    "maj6",
    "9",
    "5",
]
BASSES = ["", "/3", "/b3", "/5", "/b7", "/7", "/2", "/#5"]

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")


def run_node(cases):
    program = f"""
    const T = require({json.dumps(str(SCRIPT))});
    const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
    const out = cases.map(([kind, item, semitones, tonic, mode]) =>
      kind === "key" ? T.key(item, semitones) : T.chord(item, semitones, new T.Speller(tonic, mode)));
    process.stdout.write(JSON.stringify(out));
    """
    done = subprocess.run(
        ["node", "-e", program],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(done.stdout)


def key(tonic_pc, mode):
    return {
        "tonic_pc": tonic_pc,
        "mode": mode,
        **key_name(tonic_pc, mode),
        "scale": scale_names(tonic_pc, mode),
    }


def test_keys_move_and_are_spelled_for_the_new_key():
    cases, expected = [], []
    for mode in ("major", "minor"):
        for tonic in range(12):
            for semitones in range(-6, 7):
                cases.append(["key", key(tonic, mode), semitones, None, None])
                expected.append(key((tonic + semitones) % 12, mode))
    assert run_node(cases) == expected


def test_chords_move_and_are_spelled_for_the_new_key():
    names = ("solfege", "letter", "solfege_simple", "letter_simple", "root_pc")
    cases, expected = [], []
    for mode in ("major", "minor"):
        for tonic in range(12):
            for semitones in (-5, -1, 2, 6):
                moved = (tonic + semitones) % 12
                for root in range(12):
                    for quality in QUALITIES:
                        for bass in BASSES:
                            segment = describe_chord(f"{ROOTS[root]}:{quality}{bass}", Speller(tonic, mode))
                            cases.append(["chord", segment, semitones, moved, mode])
                            label = f"{ROOTS[(root + semitones) % 12]}:{quality}{bass}"
                            expected.append(describe_chord(label, Speller(moved, mode)))
    for got, want in zip(run_node(cases), expected, strict=True):
        assert {k: got[k] for k in names} == {k: want[k] for k in names}


def test_no_chord_and_no_transposition_stay_as_they_are():
    silence = describe_chord("N", Speller(0, "major"))
    chord = describe_chord("A:min7", Speller(0, "major"))
    assert run_node([["chord", silence, 2, 2, "major"], ["chord", chord, 0, 0, "major"]]) == [silence, chord]
