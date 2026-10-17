# Tonos

**The tempo, meter, key and chords of a song, bar by bar, worked out on your own computer.**

<p>
  <a href="https://joaquinmuzzi.github.io/Tonos/"><img src="https://img.shields.io/badge/%E2%96%B6%20Try%20the%20online%20demo-ef9f27?style=for-the-badge" alt="Try the online demo"></a>
  <a href="#installation"><img src="https://img.shields.io/badge/Install-Windows%20%C2%B7%20macOS%20%C2%B7%20Linux%20%C2%B7%20Docker-2a2a2a?style=for-the-badge" alt="Install on Windows, macOS, Linux or with Docker"></a>
</p>

[![Tests](https://github.com/joaquinmuzzi/tonos/actions/workflows/tests.yml/badge.svg)](https://github.com/joaquinmuzzi/tonos/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Drop in an audio or video file (MP4, MP3, M4A, WAV, FLAC, MKV…) and Tonos shows its chords on a
bar-by-bar grid, with a player that follows the song and an optional click on every beat, so you
can check the analysis by ear.

<!-- Demo recording: uncomment once docs/demo.gif exists.
<p align="center">
  <img src="docs/demo.gif" alt="Tonos playing a song: the click blinks on every beat and the bar being played lights up on the chord grid" width="100%">
</p>
-->

<p align="center">
  <img src="docs/screenshots/desktop.png" alt="Tonos on a computer: the top bar with play, click, speed, key and volume controls and the Separate tracks button, a timeline coloured by chord, tempo 120 bpm, meter 5/4, key D minor and the bar-by-bar chord grid" width="75%">
  <img src="docs/screenshots/phone.png" alt="Tonos on a phone: the same report in a single column" width="21.6%">
</p>

## Why Tonos?

- **Local and private.** The analysis runs on your computer and your files are never uploaded.
  The internet is only used once, to download the models.
- **Odd meters too.** Besides 3/4, 4/4 and 6/8, it finds 5/4 and 7/4 when the harmony repeats
  clearly, and it marks the grid as approximate when it is not sure where each bar starts.
- **Chords spelled for the key.** In F major you read B♭, not A♯, in letter names (C D E) or in
  solfège (Do Re Mi).
- **In Spanish.** The web app is in Spanish as well as English.
- **Says when it is unsure.** In styles that move between 3/4 and 6/8, like the chacarera or the
  zamba, it shows both readings instead of picking one in silence. Its models learned mostly from
  pop and rock, so folk and Latin American genres are worth checking by ear: see
  [how reliable it is](#how-reliable-it-is).

> [!IMPORTANT]
> **Model licensing.** The code in this repository is MIT-licensed, but the analysis relies on
> third-party model weights with their own terms: the S-KEY and Demucs weights have no stated
> licence of their own, and the Consonance-ACE weights were trained on third-party annotation
> datasets that may restrict commercial use. This project is intended for personal, local use. Commercial use of the models
> is not confirmed and may require review. See [License](#license) and
> [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Features

- **Tempo** in BPM, with its double and half, a tempo curve and a warning when the tempo drifts.
- **Meter** (3/4, 4/4, 6/8, 5/4, 7/4…), with how sure it is and the readings it could be confused
  with. Odd meters are found from how often the harmony repeats.
- **Key**, with the notes of its scale, the relative key and the model's second choice, possible
  key changes, and a warning when the recording is not tuned to A = 440 Hz.
- **Chords**, one per beat, in letter names (C D E) or solfège (Do Re Mi), in a simple
  major/minor mode or with sevenths, basses and inversions.
- A **player** with a **click** on every beat (and a light that blinks with it), a speed control
  from 0.5× to 1.5×, a timeline coloured by chord, and a **bar-by-bar grid** you can click to
  play from any bar.
- **Transpose**: move the song up or down by up to 6 semitones without changing its speed, to
  play along in another key. The key, its scale and the chords move with it, spelled for the
  new key, with the original key shown next to it.
- **Separate tracks** (optional): split the song into vocals, drums, bass and the rest with
  Demucs, then mute or solo each one while it plays. It takes about a third of the song's length
  on a CPU.
- A **command line** that prints a text report or the full JSON.

## Installation

### Windows

You need Python 3.12, [ffmpeg](https://ffmpeg.org/) and git. If one is missing, the installer
tells you the `winget` command to install it. Then, in a terminal inside this folder:

```powershell
.\install.ps1
```

It takes a few minutes and uses about 1.5 GB in `%LOCALAPPDATA%\tonos\venv`.

### macOS and Linux

You need Python 3.12, [ffmpeg](https://ffmpeg.org/) and git. If one is missing, the installer
tells you the `brew` (macOS) or `apt` (Debian, Ubuntu) command to install it. Then, in a terminal
inside this folder:

```bash
./install.sh
```

It takes a few minutes and uses about 1.5 GB in `~/.local/share/tonos/venv`. On a Mac it needs
Apple silicon: PyTorch has no current build for Intel Macs. Ubuntu releases newer than 24.04 do
not package Python 3.12; the [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa)
has it.

Running either installer again updates the environment instead of creating it from scratch.

### Docker

If you would rather not install Python, run the image, which has everything inside, the models
included, so it works offline:

```bash
docker run -p 8765:8765 ghcr.io/joaquinmuzzi/tonos
```

Then open http://127.0.0.1:8765. `-p 8765:8765` also lets other devices on your network reach the
app, which has no login; use `-p 127.0.0.1:8765:8765` to keep it on your computer. To keep the
analyses between runs, add `-v tonos-data:/data`, or use `docker compose up` in this folder,
which does both. The image is built for `linux/amd64` and `linux/arm64` (Apple silicon) and
published with each version; `docker build -t tonos .` builds it from this folder.

## Usage

- **Web app:** double-click `tonos.bat` on Windows, or run `./tonos.sh` on macOS and Linux. The
  browser opens at http://127.0.0.1:8765. Close the window (or press Ctrl+C) to stop it; if it is
  already running, only the browser opens. You can drop a file anywhere on the page, even over a
  report.
- **Command line:** `tonos.bat "C:\path\to\song.mp4"` or `./tonos.sh path/to/song.mp4` prints a
  text report; add `--json` for all the data. See the [JSON report format](docs/report-format.md)
  for the machine-readable schema. `--help` lists every option.

An analysis takes 10 to 30 seconds per song. Uploading the same file again gives the result
instantly, because it is cached. What changed in each version is in [CHANGELOG.md](CHANGELOG.md).

## How reliable it is

| What | Reliability | How it is computed |
|---|---|---|
| Tempo and beats | On solo guitar: beats with an F-measure of 79 %, tempo within 4 % in 76 % of the excerpts and in 93 % counting double or half, the typical error. Optimistic: the beat model was trained on these recordings | Beat This! (CPJKU, 2024), checked against a second method (librosa) |
| Meter | Not measured yet. In tests by hand: medium for 3/4 and 4/4; finds 5/4 and 7/4 when the harmony repeats clearly | Counts the beats between downbeats, checks it against how often the harmony and the bass repeat, and looks at whether each beat divides into 2 or 3 |
| Key | Exact for 71 % of 566 electronic dance music excerpts (weighted score 76 %). When wrong: the parallel key 7 %, a fifth away 5 %, the relative key 4 %, something else 13 %. On solo guitar, weighted score 67 % | S-KEY (Deezer, 2025), checked against a second method based on the chords |
| Chords | On solo guitar comping: right 61 % of the time for major/minor and 45 % with sevenths, from 80 % in rock and singer-songwriter songs down to 35 % in funk | Consonance-ACE (2025), one chord per beat |

These numbers were measured with [`benchmarks/run.py`](benchmarks/run.py) on two public datasets,
GuitarSet (solo guitar) and GiantSteps (electronic dance music), with Tonos 0.2.0: see
[benchmarks/results.md](benchmarks/results.md) for every metric, the caveats and how to run it
again. Neither dataset is a band with vocals, the music Tonos meets most often.

Things to keep in mind:

- **3/4 and 6/8 cannot be told apart automatically.** Some styles, like the chacarera or the
  zamba, alternate them on purpose.
- **Bars of 5 and 7:** the downbeat detector barely saw them during training and forces them
  into 4, so a second method measures how often the harmony repeats. When it is not clear on
  which beat each bar starts, the grid is marked as approximate.
- **The models were trained mostly on pop and rock sung in English.** Folk, tango and other
  Latin American genres may give worse results.
- **One key per song,** although the app warns when it finds a long stretch in another key.

## How it works

1. **Audio:** ffmpeg extracts the first non-silent audio track as a mono 22.05 kHz WAV.
2. **Beats and downbeats:** Beat This! marks them; Tonos then evens out the grid (double-time
   stretches, missed beats, mis-tracked fills) without touching real tempo changes.
3. **Tempo** comes from the mean beat interval, and is compared with librosa's estimate.
4. **Meter:** the beats between downbeats are counted, and a second method measures how
   similar the harmony, the bass and the accents are to themselves 3, 4, 5 or 7 beats later.
5. **Key:** S-KEY on the whole song and on 30-second windows, plus a key profile built from the
   chords.
6. **Chords:** Consonance-ACE on 20-second chunks, reduced to one chord per beat and spelled
   according to the key (B♭ in F major, not A♯; D/F♯, not D/G♭).

The code is in [`tonos/analysis`](tonos/analysis), one module per step.

## Where it stores things

- `%LOCALAPPDATA%\tonos\venv` on Windows, `~/.local/share/tonos/venv` on macOS and Linux: the
  Python environment the installers create.
- `%LOCALAPPDATA%\tonos\cache` (`~/.cache/tonos/cache` on macOS and Linux): finished analyses,
  small JSON files. The `TONOS_DATA_DIR` environment variable moves this folder; the Docker image
  sets it to `/data`, its volume.
- `stems`, next to `cache`: the separated tracks of the last 10 songs, about 10–15 MB each, as MP3.
- `~/.cache/torch/hub/checkpoints/`: the beat model (`beat_this-final0.ckpt`, 77 MB) and, the
  first time you separate tracks, the Demucs model (`955717e8-8726e21a.th`, 80 MB).

To uninstall, delete those and this folder. Versions before 0.1.0 used
`%LOCALAPPDATA%\analizador-musical`, which can be deleted too; version 0.1.0, called orfeo, used
`%LOCALAPPDATA%\orfeo`, which `install.ps1` renames.

## Contributing

Bug reports, wrong results and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md)
for how to set up a development environment, run the tests and write commits. Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md), and report security issues as described in
[SECURITY.md](SECURITY.md).

Ideas for the future:

- **Sections** (intro, verse, chorus), for example with SongFormer.
- **Instrument separation** with Demucs, to analyze the bass or the harmony on their own.
- **Questions in natural language** about a song, by passing the analysis JSON to a language model.

## License

The source code of this project is released under the [MIT License](LICENSE).

The machine-learning models it uses are separate works with their own terms, and this repository
does not include their weights; they are installed from their original sources:

- **Beat This!** (beats and downbeats): code and weights released under MIT by their authors.
- **S-KEY** (key): MIT code; **no licence is stated for the weights**.
- **Consonance-ACE** (chords): MIT code; the weights were trained on third-party chord annotation
  datasets whose terms **may restrict commercial use**.
- **Demucs** (separating tracks, optional): MIT code; **no licence is stated separately for the
  weights**, which were trained on a research dataset (MUSDB18-HQ) and other songs.

The web page includes the audio processor of [SoundTouchJS](https://github.com/cutterbl/SoundTouchJS),
used to transpose, under the Mozilla Public License 2.0.

Because of this, Tonos is intended for **personal, local use**. Commercial use of the model
weights is not confirmed: if you plan to use this project commercially, review each model's
licence and training-data terms first. Details, library licences and citations are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This is not legal advice.
