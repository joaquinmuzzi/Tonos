"""Nombres de notas, tonalidades y acordes en español (Do Re Mi) y en cifrado americano (C D E).

Los modelos devuelven nombres en inglés y siempre con sostenidos (A#, D#...). Acá se
traducen de forma determinística y se elige la grafía (# o ♭) según la tonalidad.
"""

from __future__ import annotations

import re

import mir_eval

LETRAS = {
    "latino": ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"],
    "americano": ["C", "D", "E", "F", "G", "A", "B"],
}
_PC_LETRA = [0, 2, 4, 5, 7, 9, 11]  # clase de altura de cada letra natural

# Ortografía preferida de la tónica (evita C# mayor, D# mayor, G# mayor, A# menor...).
_TONICA_MAYOR_BEMOL = {1, 3, 8, 10}  # Re♭, Mi♭, La♭, Si♭ mayor
_TONICA_MENOR_BEMOL = {3, 10}  # Mi♭ menor, Si♭ menor

_ESCALA = {"mayor": [0, 2, 4, 5, 7, 9, 11], "menor": [0, 2, 3, 5, 7, 8, 10]}
# Notas fuera de la escala: semitonos desde la tónica -> cuántas letras por encima de la tónica.
# Mayor: ♭II, ♭III, ♯IV, ♭VI, ♭VII (acordes prestados). Menor: ♭II, ♯III, ♯IV, ♯VI, ♯VII (sensible).
_CROMATICAS = {
    "mayor": {1: 1, 3: 2, 6: 3, 8: 5, 10: 6},
    "menor": {1: 1, 4: 2, 6: 3, 9: 5, 11: 6},
}
# Intervalo en semitonos -> cantidad de letras (3.ª = 2 letras, 5.ª = 4, 7.ª = 6...)
_LETRAS_POR_INTERVALO = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}

Nota = tuple[int, int]  # (índice de letra 0-6, alteración: -1 bemol, 0 natural, +1 sostenido)


def _alteracion(pc: int, letra: int) -> int:
    return (pc - _PC_LETRA[letra] + 6) % 12 - 6


def _nota_simple(pc: int, bemol: bool) -> Nota:
    pc %= 12
    if pc in _PC_LETRA:
        return _PC_LETRA.index(pc), 0
    return (_PC_LETRA.index((pc + 1) % 12), -1) if bemol else (_PC_LETRA.index((pc - 1) % 12), 1)


def _deletrear_tonica(tonica_pc: int, modo: str) -> Nota:
    return _nota_simple(tonica_pc, tonica_pc in (_TONICA_MAYOR_BEMOL if modo == "mayor" else _TONICA_MENOR_BEMOL))


def escribir(nota: Nota, sistema: str = "latino") -> str:
    letra, alteracion = nota
    return LETRAS[sistema][letra] + ("#" * alteracion if alteracion > 0 else "♭" * -alteracion)

_NOTA_A_PC = {
    "C": 0, "B#": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "FB": 4, "E#": 5, "F": 5,
    "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11, "CB": 11,
}


def nota_a_pc(nombre: str) -> int:
    """'Bb' / 'A#' / 'B♭' -> 10."""
    clave = nombre.strip().replace("♭", "b").replace("♯", "#")
    clave = clave[0].upper() + clave[1:].upper()
    return _NOTA_A_PC[clave]


class Ortografia:
    """Escribe las notas como lo haría un músico en la tonalidad de la canción.

    Las fundamentales se deletrean por grado de la escala (en Fa mayor: Si♭, no La#) y los
    bajos de los acordes por intervalo desde la fundamental (Re/Fa#, nunca Re/Sol♭).
    """

    def __init__(self, tonica_pc: int | None = None, modo: str | None = None):
        if tonica_pc is None or modo is None:
            tonica_pc, modo = 0, "mayor"  # sin tonalidad: como en Do mayor
        self.tonica_pc = tonica_pc % 12
        self.modo = modo
        self.tonica = _deletrear_tonica(self.tonica_pc, modo)

    def deletrear(self, pc: int) -> Nota:
        pc %= 12
        relativo = (pc - self.tonica_pc) % 12
        escala = _ESCALA[self.modo]
        sensible_menor = self.modo == "menor" and relativo == 11
        if relativo not in escala and pc in _PC_LETRA and not sensible_menor:
            # Nota fuera de la escala que es una tecla blanca: Do, no Si# (Dom en Sol# menor).
            # La sensible de una tonalidad menor sí se escribe alterada (Si#dim en Do# menor).
            return _PC_LETRA.index(pc), 0
        letras = escala.index(relativo) if relativo in escala else _CROMATICAS[self.modo][relativo]
        letra = (self.tonica[0] + letras) % 7
        alteracion = _alteracion(pc, letra)
        if abs(alteracion) > 1:  # evita dobles alteraciones (Fa𝄪 en Sol# menor -> Sol)
            return _nota_simple(pc, self.tonica[1] < 0)
        return letra, alteracion

    def sobre(self, raiz: Nota, semitonos: int, aumentada: bool = False) -> Nota:
        """La nota que está `semitonos` por encima de `raiz`, escrita como intervalo."""
        semitonos %= 12
        pasos = 4 if aumentada and semitonos == 8 else _LETRAS_POR_INTERVALO[semitonos]
        letra = (raiz[0] + pasos) % 7
        pc = (_PC_LETRA[raiz[0]] + raiz[1] + semitonos) % 12
        alteracion = _alteracion(pc, letra)
        if abs(alteracion) > 1:
            return self.deletrear(pc)
        return letra, alteracion

    def nota(self, pc: int, sistema: str = "latino") -> str:
        return escribir(self.deletrear(pc), sistema)


def nombre_tonalidad(tonica_pc: int, modo: str) -> dict:
    """Nombre de una tonalidad en ambos sistemas. modo: 'mayor' | 'menor'."""
    tonica = _deletrear_tonica(tonica_pc, modo)
    return {
        "latino": f"{escribir(tonica, 'latino')} {modo}",
        "americano": f"{escribir(tonica, 'americano')}{'m' if modo == 'menor' else ''}",
    }


def relativa(tonica_pc: int, modo: str) -> tuple[int, str]:
    """Do mayor <-> La menor."""
    if modo == "mayor":
        return (tonica_pc + 9) % 12, "menor"
    return (tonica_pc + 3) % 12, "mayor"


# --- Acordes -----------------------------------------------------------------

# Plantillas: conjunto de intervalos (semitonos desde la fundamental) -> (sufijo, sufijo simple, descripción)
_PLANTILLAS: list[tuple[frozenset[int], str, str, str]] = [
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


def _sufijos(intervalos: frozenset[int]) -> tuple[str, str, str]:
    for plantilla, sufijo, simple, descripcion in _PLANTILLAS:
        if intervalos == plantilla:
            return sufijo, simple, descripcion
    # Sin coincidencia exacta: la plantilla más grande contenida en el acorde
    # (por ejemplo, Em7 con una 11.ª agregada se muestra como Em7).
    contenidas = [p for p in _PLANTILLAS if p[0] <= intervalos and len(p[0]) >= 3]
    if contenidas:
        _, sufijo, simple, descripcion = max(contenidas, key=lambda p: len(p[0]))
        return sufijo, simple, f"{descripcion} (con notas agregadas)"
    if 4 in intervalos:
        return "", "", "mayor (con notas agregadas)"
    if 3 in intervalos:
        return "m", "m", "menor (con notas agregadas)"
    if 7 in intervalos:
        return "5", "5", "sin tercera"
    # Sin tercera ni quinta: no se puede decir si es mayor o menor
    return "(sin 3.ª)", "(sin 3.ª)", "sin tercera"


def describir_acorde(etiqueta: str, orto: Ortografia) -> dict:
    """Convierte una etiqueta Harte ('A:min7/b3', 'N') en nombres legibles.

    Devuelve un dict con: es_acorde, fundamental_pc, latino, americano,
    latino_simple, americano_simple (solo mayor/menor, más confiable) y descripcion.
    """
    if etiqueta in ("N", "X", ""):
        sin = {"latino": "—", "americano": "—", "latino_simple": "—", "americano_simple": "—"}
        return {"es_acorde": False, "fundamental_pc": None, "descripcion": "sin acorde", **sin}

    raiz, mapa, bajo = mir_eval.chord.encode(etiqueta, reduce_extended_chords=True)
    intervalos = frozenset(int(i) for i in mapa.nonzero()[0])
    sufijo, simple, descripcion = _sufijos(intervalos)
    fundamental = orto.deletrear(raiz)
    nota_bajo = None
    if bajo % 12:
        aumentado = 8 in intervalos and 7 not in intervalos
        nota_bajo = orto.sobre(fundamental, bajo, aumentada=aumentado)
    salida = {"es_acorde": True, "fundamental_pc": int(raiz), "descripcion": descripcion}
    for sistema in ("latino", "americano"):
        base = escribir(fundamental, sistema)
        nombre = base + sufijo
        if nota_bajo:
            nombre += "/" + escribir(nota_bajo, sistema)
        salida[sistema] = nombre
        salida[f"{sistema}_simple"] = base + simple
    return salida


_ETIQUETA_SKEY = re.compile(r"^([A-G][#b]?) (Major|minor)$")


def parsear_tonalidad_skey(etiqueta: str) -> tuple[int, str]:
    """'Bb Major' -> (10, 'mayor'); 'C# minor' -> (1, 'menor')."""
    m = _ETIQUETA_SKEY.match(etiqueta)
    if not m:
        raise ValueError(f"Etiqueta de tonalidad inesperada: {etiqueta!r}")
    return nota_a_pc(m.group(1)), ("mayor" if m.group(2) == "Major" else "menor")
