/*
 * Key and chord names moved up or down some semitones, spelled for the new key the same way
 * tonos/analysis/notation.py spells them for the song's key (in F major: B♭, not A#).
 * A classic script: it defines window.TonosTranspose (and module.exports, for the tests).
 */
(function (root) {
  "use strict";

  const LETTERS = {
    solfege: ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"],
    letter: ["C", "D", "E", "F", "G", "A", "B"],
  };
  const LETTER_PC = [0, 2, 4, 5, 7, 9, 11];
  const FLAT_TONICS = { major: [1, 3, 8, 10], minor: [3, 10] };
  const SCALE = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] };
  const CHROMATIC = {
    major: { 1: 1, 3: 2, 6: 3, 8: 5, 10: 6 },
    minor: { 1: 1, 4: 2, 6: 3, 9: 5, 11: 6 },
  };
  const LETTERS_PER_INTERVAL = [0, 1, 1, 2, 2, 3, 4, 4, 5, 5, 6, 6];

  const mod12 = (n) => ((n % 12) + 12) % 12;
  const accidentalOf = (pc, letter) => mod12(pc - LETTER_PC[letter] + 6) - 6;

  function simpleNote(pc, flat) {
    pc = mod12(pc);
    if (LETTER_PC.includes(pc)) return [LETTER_PC.indexOf(pc), 0];
    return flat ? [LETTER_PC.indexOf(mod12(pc + 1)), -1] : [LETTER_PC.indexOf(mod12(pc - 1)), 1];
  }

  function writeNote([letter, accidental], system) {
    return LETTERS[system][letter] + (accidental > 0 ? "#".repeat(accidental) : "♭".repeat(-accidental));
  }

  /** A port of notation.Speller: spells notes by their degree in a key. */
  class Speller {
    constructor(tonicPc, mode) {
      this.tonicPc = mod12(tonicPc);
      this.mode = mode;
      this.tonic = simpleNote(this.tonicPc, FLAT_TONICS[mode].includes(this.tonicPc));
    }

    spell(pc) {
      pc = mod12(pc);
      const relative = mod12(pc - this.tonicPc);
      const scale = SCALE[this.mode];
      const minorLeadingTone = this.mode === "minor" && relative === 11;
      if (!scale.includes(relative) && LETTER_PC.includes(pc) && !minorLeadingTone) return [LETTER_PC.indexOf(pc), 0];
      const letters = scale.includes(relative) ? scale.indexOf(relative) : CHROMATIC[this.mode][relative];
      const letter = (this.tonic[0] + letters) % 7;
      const accidental = accidentalOf(pc, letter);
      if (Math.abs(accidental) > 1) return simpleNote(pc, this.tonic[1] < 0);
      return [letter, accidental];
    }

    above(rootNote, semitones, augmented) {
      semitones = mod12(semitones);
      const steps = augmented && semitones === 8 ? 4 : LETTERS_PER_INTERVAL[semitones];
      const letter = (rootNote[0] + steps) % 7;
      const pc = mod12(LETTER_PC[rootNote[0]] + rootNote[1] + semitones);
      const accidental = accidentalOf(pc, letter);
      if (Math.abs(accidental) > 1) return this.spell(pc);
      return [letter, accidental];
    }
  }

  function notePc(letter, accidentals) {
    let pc = LETTER_PC[LETTERS.letter.indexOf(letter)];
    for (const sign of accidentals) pc += sign === "#" ? 1 : -1;
    return mod12(pc);
  }

  /** A key ({tonic_pc, mode, solfege, letter, scale?}) moved by `semitones`. */
  function key(original, semitones) {
    if (!semitones || original.tonic_pc === null || original.tonic_pc === undefined) return original;
    const speller = new Speller(original.tonic_pc + semitones, original.mode);
    const moved = { ...original, tonic_pc: speller.tonicPc };
    for (const system of ["solfege", "letter"]) moved[system] = writeNote(speller.tonic, system);
    if (original.scale) {
      moved.scale = {};
      for (const system of ["solfege", "letter"]) {
        moved.scale[system] = SCALE[original.mode].map((step) => writeNote(speller.spell(speller.tonicPc + step), system));
      }
    }
    return moved;
  }

  const CHORD = /^([A-G])([#♭]*)([^/]*)(?:\/([A-G])([#♭]*))?$/;
  const ROOT = /^[A-G][#♭]*/;
  // Chords without a fifth: a bass a minor sixth above their root is a sharp fifth (C°/G#)
  const NO_FIFTH = ["dim", "dim7", "m7(♭5)", "aug"];

  /**
   * A chord segment's names moved by `semitones`, spelled by `speller` (a Speller of the
   * moved key). The suffix (m7, sus4...) and the bass's interval above the root stay.
   */
  function chord(segment, semitones, speller) {
    if (!semitones || !segment || !segment.is_chord || segment.root_pc === null) return segment;
    const parts = CHORD.exec(segment.letter);
    if (!parts) return segment;
    const [, , , suffix, bassLetter, bassAccidentals] = parts;
    const simple = segment.letter_simple.replace(ROOT, "");
    const rootNote = speller.spell(segment.root_pc + semitones);
    const bass = bassLetter
      ? speller.above(rootNote, notePc(bassLetter, bassAccidentals) - segment.root_pc, NO_FIFTH.includes(suffix))
      : null;
    const moved = { ...segment, root_pc: mod12(segment.root_pc + semitones) };
    for (const system of ["solfege", "letter"]) {
      const base = writeNote(rootNote, system);
      moved[system] = base + suffix + (bass ? "/" + writeNote(bass, system) : "");
      moved[`${system}_simple`] = base + simple;
    }
    return moved;
  }

  const api = { Speller, key, chord };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TonosTranspose = api;
})(typeof window !== "undefined" ? window : globalThis);
