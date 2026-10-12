"""Note, key and chord names in solfège (Do Re Mi) and in letter notation (C D E).

The models return English names, always with sharps (A#, D#...). Here they are translated
deterministically and spelled with sharps or flats (# or ♭) according to the key.
"""

from __future__ import annotations

import re

import mir_eval

LETTERS = {
    "solfege": ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"],
    "letter": ["C", "D", "E", "F", "G", "A", "B"],
}
_LETTER_PC = [0, 2, 4, 5, 7, 9, 11]  # pitch class of each natural letter

# Preferred spelling of the tonic (avoids C# major, D# major, G# major, A# minor...).
_FLAT_MAJOR_TONICS = {1, 3, 8, 10}  # D♭, E♭, A♭, B♭ major
_FLAT_MINOR_TONICS = {3, 10}  # E♭ minor, B♭ minor

_SCALE = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
# Out-of-scale notes: semitones above the tonic -> how many letters above the tonic.
# Major: ♭II, ♭III, ♯IV, ♭VI, ♭VII (borrowed chords). Minor: ♭II, ♯III, ♯IV, ♯VI, ♯VII (leading tone).
_CHROMATIC = {
    "major": {1: 1, 3: 2, 6: 3, 8: 5, 10: 6},
    "minor": {1: 1, 4: 2, 6: 3, 9: 5, 11: 6},
}
# Interval in semitones -> number of letters (3rd = 2 letters, 5th = 4, 7th = 6...)
_LETTERS_PER_INTERVAL = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}

Note = tuple[int, int]  # (letter index 0-6, accidental: -1 flat, 0 natural, +1 sharp)


def _accidental(pc: int, letter: int) -> int:
    return (pc - _LETTER_PC[letter] + 6) % 12 - 6


def _simple_note(pc: int, flat: bool) -> Note:
    pc %= 12
    if pc in _LETTER_PC:
        return _LETTER_PC.index(pc), 0
    return (_LETTER_PC.index((pc + 1) % 12), -1) if flat else (_LETTER_PC.index((pc - 1) % 12), 1)


def _spell_tonic(tonic_pc: int, mode: str) -> Note:
    return _simple_note(tonic_pc, tonic_pc in (_FLAT_MAJOR_TONICS if mode == "major" else _FLAT_MINOR_TONICS))


def write_note(name: Note, system: str = "solfege") -> str:
    letter, accidental = name
    return LETTERS[system][letter] + ("#" * accidental if accidental > 0 else "♭" * -accidental)


_NOTE_TO_PC = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "FB": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
    "CB": 11,
}


def note_to_pc(name: str) -> int:
    """'Bb' / 'A#' / 'B♭' -> 10."""
    normalized = name.strip().replace("♭", "b").replace("♯", "#")
    normalized = normalized[0].upper() + normalized[1:].upper()
    return _NOTE_TO_PC[normalized]


class Speller:
    """Spells notes the way a musician would in the key of the song.

    Chord roots are spelled by scale degree (in F major: B♭, not A#) and chord basses by
    their interval above the root (D/F#, never D/G♭).
    """

    def __init__(self, tonic_pc: int | None = None, mode: str | None = None):
        if tonic_pc is None or mode is None:
            tonic_pc, mode = 0, "major"  # no key: spell as in C major
        self.tonic_pc = tonic_pc % 12
        self.mode = mode
        self.tonic = _spell_tonic(self.tonic_pc, mode)

    def spell(self, pc: int) -> Note:
        pc %= 12
        relative = (pc - self.tonic_pc) % 12
        scale = _SCALE[self.mode]
        minor_leading_tone = self.mode == "minor" and relative == 11
        if relative not in scale and pc in _LETTER_PC and not minor_leading_tone:
            # An out-of-scale note on a white key is written natural: C, not B# (Cm in G# minor).
            # The leading tone of a minor key does keep its accidental (B#dim in C# minor).
            return _LETTER_PC.index(pc), 0
        letters = scale.index(relative) if relative in scale else _CHROMATIC[self.mode][relative]
        letter = (self.tonic[0] + letters) % 7
        accidental = _accidental(pc, letter)
        if abs(accidental) > 1:  # avoid double accidentals (F𝄪 in G# minor -> G)
            return _simple_note(pc, self.tonic[1] < 0)
        return letter, accidental

    def above(self, root: Note, semitones: int, augmented: bool = False) -> Note:
        """The note `semitones` above `root`, spelled as an interval."""
        semitones %= 12
        steps = 4 if augmented and semitones == 8 else _LETTERS_PER_INTERVAL[semitones]
        letter = (root[0] + steps) % 7
        pc = (_LETTER_PC[root[0]] + root[1] + semitones) % 12
        accidental = _accidental(pc, letter)
        if abs(accidental) > 1:
            return self.spell(pc)
        return letter, accidental

    def name(self, pc: int, system: str = "solfege") -> str:
        return write_note(self.spell(pc), system)


def key_name(tonic_pc: int, mode: str) -> dict:
    """Name of the tonic of a key in both notations (mode: 'major' | 'minor')."""
    tonic = _spell_tonic(tonic_pc, mode)
    return {"solfege": write_note(tonic, "solfege"), "letter": write_note(tonic, "letter")}


def relative_key(tonic_pc: int, mode: str) -> tuple[int, str]:
    """C major <-> A minor."""
    if mode == "major":
        return (tonic_pc + 9) % 12, "minor"
    return (tonic_pc + 3) % 12, "major"


# --- Chords -------------------------------------------------------------------

# Templates: set of intervals (semitones above the root) -> (suffix, simple suffix, description)
_TEMPLATES: list[tuple[frozenset[int], str, str, str]] = [
    (frozenset({0, 4, 7}), "", "", "major"),
    (frozenset({0, 3, 7}), "m", "m", "minor"),
    (frozenset({0, 4, 7, 10}), "7", "", "dominant seventh"),
    (frozenset({0, 4, 7, 11}), "maj7", "", "major seventh"),
    (frozenset({0, 3, 7, 10}), "m7", "m", "minor seventh"),
    (frozenset({0, 3, 7, 11}), "m(maj7)", "m", "minor major seventh"),
    (frozenset({0, 3, 6}), "dim", "dim", "diminished"),
    (frozenset({0, 3, 6, 9}), "dim7", "dim", "diminished seventh"),
    (frozenset({0, 3, 6, 10}), "m7(♭5)", "dim", "half-diminished"),
    (frozenset({0, 4, 8}), "aug", "aug", "augmented"),
    # No third: neither major nor minor, so the simple names keep them as they are
    (frozenset({0, 5, 7}), "sus4", "sus4", "suspended fourth"),
    (frozenset({0, 2, 7}), "sus2", "sus2", "suspended second"),
    (frozenset({0, 5, 7, 10}), "7sus4", "sus4", "seventh with suspended fourth"),
    (frozenset({0, 4, 7, 9}), "6", "", "sixth"),
    (frozenset({0, 3, 7, 9}), "m6", "m", "minor sixth"),
    (frozenset({0, 2, 4, 7}), "add9", "", "added ninth"),
    (frozenset({0, 2, 3, 7}), "m(add9)", "m", "minor added ninth"),
    (frozenset({0, 2, 4, 7, 10}), "9", "", "ninth"),
    (frozenset({0, 2, 4, 7, 11}), "maj9", "", "major ninth"),
    (frozenset({0, 2, 3, 7, 10}), "m9", "m", "minor ninth"),
    (frozenset({0, 7}), "5", "5", "fifth (power chord)"),
    (frozenset({0, 4}), "", "", "major (no fifth)"),
    (frozenset({0, 3}), "m", "m", "minor (no fifth)"),
]


def _suffixes(intervals: frozenset[int]) -> tuple[str, str, str]:
    for template, suffix, simple, description in _TEMPLATES:
        if intervals == template:
            return suffix, simple, description
    # No exact match: the largest template contained in the chord
    # (for example, Em7 with an added 11th is shown as Em7).
    contained = [p for p in _TEMPLATES if p[0] <= intervals and len(p[0]) >= 3]
    if contained:
        _, suffix, simple, description = max(contained, key=lambda p: len(p[0]))
        return suffix, simple, f"{description} (with added notes)"
    if 4 in intervals:
        return "", "", "major (with added notes)"
    if 3 in intervals:
        return "m", "m", "minor (with added notes)"
    if 7 in intervals:
        return "5", "5", "no third"
    # Neither third nor fifth: it cannot be called major or minor
    return "(no3)", "(no3)", "no third"


def describe_chord(label: str, speller: Speller) -> dict:
    """Turns a Harte label ('A:min7/b3', 'N') into readable names.

    Returns a dict with: is_chord, root_pc, solfege, letter, solfege_simple, letter_simple
    (major/minor only, more reliable) and description.
    """
    if label in ("N", "X", ""):
        no_names = {"solfege": "—", "letter": "—", "solfege_simple": "—", "letter_simple": "—"}
        return {"is_chord": False, "root_pc": None, "description": "no chord", **no_names}

    root, bitmap, bass = mir_eval.chord.encode(label, reduce_extended_chords=True)
    intervals = frozenset(int(i) for i in bitmap.nonzero()[0])
    suffix, simple, description = _suffixes(intervals)
    spelled_root = speller.spell(root)
    bass_note = None
    if bass % 12:
        is_augmented = 8 in intervals and 7 not in intervals
        bass_note = speller.above(spelled_root, bass, augmented=is_augmented)
    output = {"is_chord": True, "root_pc": int(root), "description": description}
    for system in ("solfege", "letter"):
        base = write_note(spelled_root, system)
        name = base + suffix
        if bass_note:
            name += "/" + write_note(bass_note, system)
        output[system] = name
        output[f"{system}_simple"] = base + simple
    return output


_SKEY_LABEL = re.compile(r"^([A-G][#b]?) (Major|minor)$")


def parse_skey_label(label: str) -> tuple[int, str]:
    """'Bb Major' -> (10, 'major'); 'C# minor' -> (1, 'minor')."""
    m = _SKEY_LABEL.match(label)
    if not m:
        raise ValueError(f"unexpected key label: {label!r}")
    return note_to_pc(m.group(1)), ("major" if m.group(2) == "Major" else "minor")
