"""Nombres de notas, tonalidades y acordes en español (Do Re Mi) y en cifrado americano (C D E).

Los modelos devuelven nombres en inglés y siempre con sostenidos (A#, D#...). Acá se
traducen de forma determinística y se elige la grafía (# o ♭) según la tonalidad.
"""

from __future__ import annotations

import re

import mir_eval

LETTERS = {
    "latino": ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"],
    "americano": ["C", "D", "E", "F", "G", "A", "B"],
}
_LETTER_PC = [0, 2, 4, 5, 7, 9, 11]  # clase de altura de cada letra natural

# Ortografía preferida de la tónica (evita C# mayor, D# mayor, G# mayor, A# menor...).
_FLAT_MAJOR_TONICS = {1, 3, 8, 10}  # Re♭, Mi♭, La♭, Si♭ mayor
_FLAT_MINOR_TONICS = {3, 10}  # Mi♭ menor, Si♭ menor

_SCALE = {"mayor": [0, 2, 4, 5, 7, 9, 11], "menor": [0, 2, 3, 5, 7, 8, 10]}
# Notas fuera de la escala: semitonos desde la tónica -> cuántas letras por encima de la tónica.
# Mayor: ♭II, ♭III, ♯IV, ♭VI, ♭VII (acordes prestados). Menor: ♭II, ♯III, ♯IV, ♯VI, ♯VII (sensible).
_CHROMATIC = {
    "mayor": {1: 1, 3: 2, 6: 3, 8: 5, 10: 6},
    "menor": {1: 1, 4: 2, 6: 3, 9: 5, 11: 6},
}
# Intervalo en semitonos -> cantidad de letras (3.ª = 2 letras, 5.ª = 4, 7.ª = 6...)
_LETTERS_PER_INTERVAL = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}

Note = tuple[int, int]  # (índice de letra 0-6, alteración: -1 bemol, 0 natural, +1 sostenido)


def _accidental(pc: int, letter: int) -> int:
    return (pc - _LETTER_PC[letter] + 6) % 12 - 6


def _simple_note(pc: int, flat: bool) -> Note:
    pc %= 12
    if pc in _LETTER_PC:
        return _LETTER_PC.index(pc), 0
    return (_LETTER_PC.index((pc + 1) % 12), -1) if flat else (_LETTER_PC.index((pc - 1) % 12), 1)


def _spell_tonic(tonic_pc: int, mode: str) -> Note:
    return _simple_note(tonic_pc, tonic_pc in (_FLAT_MAJOR_TONICS if mode == "mayor" else _FLAT_MINOR_TONICS))


def write_note(name: Note, system: str = "latino") -> str:
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
    key_id = name.strip().replace("♭", "b").replace("♯", "#")
    key_id = key_id[0].upper() + key_id[1:].upper()
    return _NOTE_TO_PC[key_id]


class Speller:
    """Escribe las notas como lo haría un músico en la tonalidad de la canción.

    Las fundamentales se deletrean por grado de la escala (en Fa mayor: Si♭, no La#) y los
    bajos de los acordes por intervalo desde la fundamental (Re/Fa#, nunca Re/Sol♭).
    """

    def __init__(self, tonic_pc: int | None = None, mode: str | None = None):
        if tonic_pc is None or mode is None:
            tonic_pc, mode = 0, "mayor"  # sin tonalidad: como en Do mayor
        self.tonic_pc = tonic_pc % 12
        self.mode = mode
        self.tonic = _spell_tonic(self.tonic_pc, mode)

    def spell(self, pc: int) -> Note:
        pc %= 12
        relative = (pc - self.tonic_pc) % 12
        scale = _SCALE[self.mode]
        minor_leading_tone = self.mode == "menor" and relative == 11
        if relative not in scale and pc in _LETTER_PC and not minor_leading_tone:
            # Nota fuera de la escala que es una tecla blanca: Do, no Si# (Dom en Sol# menor).
            # La sensible de una tonalidad menor sí se escribe alterada (Si#dim en Do# menor).
            return _LETTER_PC.index(pc), 0
        letters = scale.index(relative) if relative in scale else _CHROMATIC[self.mode][relative]
        letter = (self.tonic[0] + letters) % 7
        accidental = _accidental(pc, letter)
        if abs(accidental) > 1:  # evita dobles alteraciones (Fa𝄪 en Sol# menor -> Sol)
            return _simple_note(pc, self.tonic[1] < 0)
        return letter, accidental

    def above(self, root: Note, semitones: int, augmented: bool = False) -> Note:
        """La nota que está `semitonos` por encima de `raiz`, escrita como intervalo."""
        semitones %= 12
        steps = 4 if augmented and semitones == 8 else _LETTERS_PER_INTERVAL[semitones]
        letter = (root[0] + steps) % 7
        pc = (_LETTER_PC[root[0]] + root[1] + semitones) % 12
        accidental = _accidental(pc, letter)
        if abs(accidental) > 1:
            return self.spell(pc)
        return letter, accidental

    def name(self, pc: int, system: str = "latino") -> str:
        return write_note(self.spell(pc), system)


def key_name(tonic_pc: int, mode: str) -> dict:
    """Nombre de una tonalidad en ambos sistemas. modo: 'mayor' | 'menor'."""
    tonic = _spell_tonic(tonic_pc, mode)
    return {
        "latino": f"{write_note(tonic, 'latino')} {mode}",
        "americano": f"{write_note(tonic, 'americano')}{'m' if mode == 'menor' else ''}",
    }


def relative_key(tonic_pc: int, mode: str) -> tuple[int, str]:
    """Do mayor <-> La menor."""
    if mode == "mayor":
        return (tonic_pc + 9) % 12, "menor"
    return (tonic_pc + 3) % 12, "mayor"


# --- Acordes -----------------------------------------------------------------

# Plantillas: conjunto de intervalos (semitonos desde la fundamental) -> (sufijo, sufijo simple, descripción)
_TEMPLATES: list[tuple[frozenset[int], str, str, str]] = [
    (frozenset({0, 4, 7}), "", "", "mayor"),
    (frozenset({0, 3, 7}), "m", "m", "menor"),
    (frozenset({0, 4, 7, 10}), "7", "", "séptima de dominante"),
    (frozenset({0, 4, 7, 11}), "maj7", "", "séptima mayor"),
    (frozenset({0, 3, 7, 10}), "m7", "m", "menor con séptima"),
    (frozenset({0, 3, 7, 11}), "m(maj7)", "m", "menor con séptima mayor"),
    (frozenset({0, 3, 6}), "dim", "dim", "disminuido"),
    (frozenset({0, 3, 6, 9}), "dim7", "dim", "disminuido con séptima"),
    (frozenset({0, 3, 6, 10}), "m7(♭5)", "dim", "semidisminuido"),
    (frozenset({0, 4, 8}), "aug", "aug", "aumentado"),
    # Sin tercera: no son ni mayores ni menores, así que el modo simple los deja como están
    (frozenset({0, 5, 7}), "sus4", "sus4", "suspendido de cuarta"),
    (frozenset({0, 2, 7}), "sus2", "sus2", "suspendido de segunda"),
    (frozenset({0, 5, 7, 10}), "7sus4", "sus4", "séptima con cuarta suspendida"),
    (frozenset({0, 4, 7, 9}), "6", "", "sexta"),
    (frozenset({0, 3, 7, 9}), "m6", "m", "menor con sexta"),
    (frozenset({0, 2, 4, 7}), "add9", "", "con novena agregada"),
    (frozenset({0, 2, 3, 7}), "m(add9)", "m", "menor con novena agregada"),
    (frozenset({0, 2, 4, 7, 10}), "9", "", "novena"),
    (frozenset({0, 2, 4, 7, 11}), "maj9", "", "novena mayor"),
    (frozenset({0, 2, 3, 7, 10}), "m9", "m", "menor con novena"),
    (frozenset({0, 7}), "5", "5", "quinta (power chord)"),
    (frozenset({0, 4}), "", "", "mayor (sin quinta)"),
    (frozenset({0, 3}), "m", "m", "menor (sin quinta)"),
]


def _suffixes(intervals: frozenset[int]) -> tuple[str, str, str]:
    for template, suffix, simple, description in _TEMPLATES:
        if intervals == template:
            return suffix, simple, description
    # Sin coincidencia exacta: la plantilla más grande contenida en el acorde
    # (por ejemplo, Em7 con una 11.ª agregada se muestra como Em7).
    contained = [p for p in _TEMPLATES if p[0] <= intervals and len(p[0]) >= 3]
    if contained:
        _, suffix, simple, description = max(contained, key=lambda p: len(p[0]))
        return suffix, simple, f"{description} (con notas agregadas)"
    if 4 in intervals:
        return "", "", "mayor (con notas agregadas)"
    if 3 in intervals:
        return "m", "m", "menor (con notas agregadas)"
    if 7 in intervals:
        return "5", "5", "sin tercera"
    # Sin tercera ni quinta: no se puede decir si es mayor o menor
    return "(sin 3.ª)", "(sin 3.ª)", "sin tercera"


def describe_chord(label: str, speller: Speller) -> dict:
    """Convierte una etiqueta Harte ('A:min7/b3', 'N') en nombres legibles.

    Devuelve un dict con: es_acorde, fundamental_pc, latino, americano,
    latino_simple, americano_simple (solo mayor/menor, más confiable) y descripcion.
    """
    if label in ("N", "X", ""):
        empty = {"latino": "—", "americano": "—", "latino_simple": "—", "americano_simple": "—"}
        return {"es_acorde": False, "fundamental_pc": None, "descripcion": "sin acorde", **empty}

    root, bitmap, bass = mir_eval.chord.encode(label, reduce_extended_chords=True)
    intervals = frozenset(int(i) for i in bitmap.nonzero()[0])
    suffix, simple, description = _suffixes(intervals)
    spelled_root = speller.spell(root)
    bass_note = None
    if bass % 12:
        is_augmented = 8 in intervals and 7 not in intervals
        bass_note = speller.above(spelled_root, bass, augmented=is_augmented)
    output = {"es_acorde": True, "fundamental_pc": int(root), "descripcion": description}
    for system in ("latino", "americano"):
        base = write_note(spelled_root, system)
        name = base + suffix
        if bass_note:
            name += "/" + write_note(bass_note, system)
        output[system] = name
        output[f"{system}_simple"] = base + simple
    return output


_SKEY_LABEL = re.compile(r"^([A-G][#b]?) (Major|minor)$")


def parse_skey_label(label: str) -> tuple[int, str]:
    """'Bb Major' -> (10, 'mayor'); 'C# minor' -> (1, 'menor')."""
    m = _SKEY_LABEL.match(label)
    if not m:
        raise ValueError(f"Etiqueta de tonalidad inesperada: {label!r}")
    return note_to_pc(m.group(1)), ("mayor" if m.group(2) == "Major" else "menor")
