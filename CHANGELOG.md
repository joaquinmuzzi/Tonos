# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the version is 0.x,
minor versions may include breaking changes; they are always listed under **Changed** with a
note on what to update.

## [Unreleased]

### Fixed

- Songs with a single instrument, pauses or a free tempo, where the beat detector jumps between
  the beat and the notes of a triplet (a guitar ballad at 83 BPM came out at 246 BPM in 3/4): when
  the detected beats are irregular, the beat is estimated again at a steady tempo, the one at which
  the harmony repeats most clearly, and the report says so.

## [0.2.0] - 2026-10-12

### Changed

- The project is now called **Tonos** (it was orfeo). It runs with `python -m tonos` and
  `tonos.bat`, keeps its data in `%LOCALAPPDATA%\tonos` (`~/.cache/tonos` elsewhere), and the
  report says `tonos_version`. Run `install.ps1` again: it renames the old `orfeo` folder, so
  nothing is downloaded again.

### Fixed

- Bars in 5/4 and 7/4 start on the right beat in more songs: the bar position now follows the
  bass and the chord changes (also when chords are anticipated by half a beat), instead of the
  beat where the harmony changes the most.
- `install.ps1` keeps its window open when it is started from Explorer (right-click > Run with
  PowerShell), so its result or its error can be read, and it reports errors as a single
  `ERROR:` line.

## [0.1.0] - 2026-10-12

First public release.

### Added

- Local web app and command line that analyze an audio or video file (MP4, MP3, M4A, WAV,
  FLAC, MKV...) and report its tempo, meter, key and chords, bar by bar. Nothing leaves the
  computer.
- Beats and downbeats with Beat This!, key with S-KEY and chords with Consonance-ACE, each
  checked against a second, independent method to estimate how reliable the result is.
- Meter from how often the harmony and the bass repeat, which finds 5/4 and 7/4 where the
  downbeat detector forces 4/4. The bars are placed from the attacks, the chord changes (also
  when chords are anticipated) and the beat detector, weighing each by how consistent it is.
- Correction of uneven beat grids (double-time stretches, missed beats, mis-tracked drum
  fills) and of bars cut by a wrong downbeat, without touching real tempo changes.
- Note, key and chord names spelled according to the key, in letter names (C D E) and in
  solfège (Do Re Mi), in a simple major/minor mode or in full.
- Player with the current and next chord, the beat count, an optional click on every beat and
  a bar-by-bar grid to play from any bar.
- Interface in English and Spanish, chosen from the browser's language.
- Cache of finished analyses, and JSON export of the full report.
- Windows installer (`install.ps1`) and launcher (`orfeo.bat`).
- `python -m orfeo --version`, and the orfeo version inside every report.
- Tests with synthetic songs, CI on every pull request, Dependabot and Ruff.

### Changed

Compared with the unreleased prototype, everything is now in English. If you used it:

- The app runs with `python -m orfeo` (it was `python -m app`), and the scripts are
  `install.ps1` and `orfeo.bat` (they were `instalar.ps1` and `iniciar.bat`).
- Command-line flags: `--port`, `--no-browser` and `--preload` (they were `--puerto`,
  `--no-abrir` and `--precargar`).
- The JSON report has English keys and message codes, and the API is under `/api/analyses`.
- Data lives in `%LOCALAPPDATA%\orfeo`. Run `install.ps1` again to create the new environment;
  the old `%LOCALAPPDATA%\analizador-musical` folder can then be deleted (its saved analyses use
  the old report format and would be recomputed anyway).

[Unreleased]: https://github.com/joaquinmuzzi/tonos/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/joaquinmuzzi/tonos/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joaquinmuzzi/tonos/releases/tag/v0.1.0
