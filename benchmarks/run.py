"""Measures how accurate Tonos is on public datasets, with the standard metrics of mir_eval.

    python benchmarks/run.py --download            # downloads the datasets (about 1.6 GB) and runs
    python benchmarks/run.py --data-dir D:/mir     # the datasets are already in D:/mir
    python benchmarks/run.py --dataset guitarset --limit 20

Datasets (see benchmarks/results.md for their licences):

- GuitarSet: 360 excerpts of solo guitar with chords, beats, tempo and key.
- GiantSteps+ EDM Key: 600 two-minute excerpts of electronic dance music with their key.

The result of every track is kept in <data-dir>/results/<dataset>/, so a run that is interrupted
continues where it stopped. The summary is written to benchmarks/results.md and the scores of
every track to benchmarks/results/<dataset>.csv.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import time
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import mir_eval
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tonos import __version__  # noqa: E402
from tonos.analysis import pipeline  # noqa: E402

HERE = ROOT / "benchmarks"
SKIPPED: dict[str, Counter] = {}  # tracks left out of each dataset, and why, for the report
# GuitarSet's styles, from the track names (00_BN1-129-Eb_comp...)
STYLES = {"BN": "Bossa nova", "Funk": "Funk", "Jazz": "Jazz", "Rock": "Rock", "SS": "Singer-songwriter"}
KEY_CATEGORIES = {1.0: "correct", 0.5: "fifth", 0.3: "relative", 0.2: "parallel", 0.0: "other"}


@dataclass(frozen=True)
class Remote:
    url: str
    md5: str
    size: int


@dataclass(frozen=True)
class Dataset:
    name: str
    title: str
    source: str
    license: str
    remotes: tuple[Remote, ...]


DATASETS = {
    "guitarset": Dataset(
        "guitarset",
        "GuitarSet",
        "https://zenodo.org/records/3371780",
        "CC BY 4.0",
        (
            Remote(
                "https://zenodo.org/api/records/3371780/files/annotation.zip/content",
                "b39b78e63d3446f2e54ddb7a54df9b10",
                39_132_574,
            ),
            Remote(
                "https://zenodo.org/api/records/3371780/files/audio_mono-mic.zip/content",
                "275966d6610ac34999b58426beb119c3",
                656_927_981,
            ),
        ),
    ),
    "giantsteps_key": Dataset(
        "giantsteps_key",
        "GiantSteps+ EDM Key",
        "https://zenodo.org/records/1095691",
        "CC BY-SA 4.0",
        (
            Remote(
                "https://zenodo.org/api/records/1095691/files/keys.zip/content",
                "775b7d17e009f5818544cf505b6a96fd",
                168_382,
            ),
            Remote(
                "https://zenodo.org/api/records/1095691/files/audio.zip/content",
                "8ec9ade888d5a88ce435d7fda031929b",
                855_761_126,
            ),
        ),
    ),
}


# ---------------------------------------------------------------- download


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(dataset: Dataset, folder: Path) -> None:
    """Downloads and unpacks the dataset's files, checking their MD5; skips what is already there."""
    folder.mkdir(parents=True, exist_ok=True)
    for remote in dataset.remotes:
        name = remote.url.split("/files/")[1].split("/")[0]
        target = folder / name
        done = folder / f".{name}.unpacked"
        if done.exists():
            continue
        if not target.exists() or target.stat().st_size != remote.size or _md5(target) != remote.md5:
            print(f"Downloading {name} ({remote.size / 1e6:.0f} MB) from {dataset.source}")
            urllib.request.urlretrieve(remote.url, target)
            if _md5(target) != remote.md5:
                raise SystemExit(f"{name}: the MD5 does not match; delete it and try again")
        print(f"Unpacking {name}")
        # Each archive in its own folder: some have a folder inside and some do not
        with zipfile.ZipFile(target) as z:
            z.extractall(folder / name.removesuffix(".zip"))
        done.touch()


# ---------------------------------------------------------------- references


@dataclass
class Track:
    id: str
    audio: Path
    reference: dict


def _harte_key(text: str) -> tuple[str | None, str]:
    """'Bb minor dorian' -> ('Bb minor', ''); modes count as major or minor.

    Anything else gives (None, why): the track is left out and the report counts it.
    """
    words = text.replace(":", " ").split()
    if len(words) < 2:
        return None, "no key"
    tonic, mode = words[0], words[1].lower()
    minor = {"minor", "aeolian", "dorian", "phrygian", "locrian"}
    major = {"major", "ionian", "lydian", "mixolydian"}
    mode = "minor" if mode in minor else "major" if mode in major else None
    if mode is None:
        return None, "neither major nor minor"
    try:
        mir_eval.key.validate_key(f"{tonic} {mode}")
    except ValueError:
        return None, "not a valid key name"  # a few annotations have typos, such as "D_"
    return f"{tonic} {mode}", ""


def _files(folder: Path, pattern: str) -> list[Path]:
    """Files under the folder, without the copies macOS leaves in archives (__MACOSX, ._*)."""
    return sorted(
        p for p in folder.rglob(pattern) if "__MACOSX" not in p.parts and not p.name.startswith("._")
    )


def giantsteps_tracks(folder: Path) -> list[Track]:
    # Both the audio and the key files are named "<Beatport id> <artist> - <title>"
    audio = {p.name.split(" ")[0]: p for p in _files(folder, "*.mp3")}
    tracks = []
    for path in _files(folder, "*.txt"):
        track_id = path.name.split(" ")[0]
        key, why = _harte_key(path.read_text(encoding="utf-8", errors="replace").strip())
        if track_id not in audio:
            continue
        if key:
            tracks.append(Track(track_id, audio[track_id], {"key": key}))
        else:
            SKIPPED.setdefault("giantsteps_key", Counter())[why] += 1
    return tracks


def _observations(annotation: dict) -> list[dict]:
    return annotation["data"]


def guitarset_tracks(folder: Path) -> list[Track]:
    audio_files = {p.name.removesuffix("_mic.wav"): p for p in _files(folder, "*_mic.wav")}
    tracks = []
    for path in _files(folder, "*.jams"):
        audio = audio_files.get(path.stem)
        if audio is None:
            continue
        jam = json.loads(path.read_text(encoding="utf-8"))
        by_namespace: dict[str, list[dict]] = {}
        for annotation in jam["annotations"]:
            by_namespace.setdefault(annotation["namespace"], []).append(annotation)
        # Two chord annotations: the lead sheet the player read, and the chords inferred from
        # what was played (see GuitarSet's documentation)
        chords = by_namespace["chord"]
        leadsheet, performed = chords[0], chords[1]
        beats = [o["time"] for o in _observations(by_namespace["beat_position"][0])]
        tempo = _observations(by_namespace["tempo"][0])[0]["value"]
        key = _observations(by_namespace["key_mode"][0])[0]["value"]
        tracks.append(
            Track(
                path.stem,
                audio,
                {
                    "chords_leadsheet": [
                        (o["time"], o["time"] + o["duration"], o["value"]) for o in leadsheet["data"]
                    ],
                    "chords_performed": [
                        (o["time"], o["time"] + o["duration"], o["value"]) for o in performed["data"]
                    ],
                    "beats": beats,
                    "tempo": float(tempo),
                    "key": _harte_key(key)[0],
                    "style": "comp" if path.stem.endswith("_comp") else "solo",
                },
            )
        )
    return tracks


TRACKS = {"guitarset": guitarset_tracks, "giantsteps_key": giantsteps_tracks}


# ---------------------------------------------------------------- metrics


def _mir_eval_key(best: dict) -> str:
    """Tonos' best key ('B♭', 'minor') in mir_eval's format ('Bb minor')."""
    return f"{best['letter'].replace('♭', 'b').replace('♯', '#')} {best['mode']}"


def _valid_chord(label: str) -> str:
    try:
        mir_eval.chord.validate_chord_label(label)
        return label
    except mir_eval.chord.InvalidChordException:
        return "X"  # mir_eval ignores X, and it is counted apart


def chord_scores(reference: list[tuple], result: dict) -> dict:
    ref_intervals = np.array([[s, e] for s, e, _ in reference])
    ref_labels = [label for _, _, label in reference]
    segments = result["chords"]["segments"]
    est_intervals = np.array([[s["start"], s["end"]] for s in segments])
    est_labels = [_valid_chord(s["label"]) for s in segments]
    est_intervals, est_labels = mir_eval.util.adjust_intervals(
        est_intervals, est_labels, ref_intervals.min(), ref_intervals.max(), "N", "N"
    )
    merged, ref, est = mir_eval.util.merge_labeled_intervals(
        ref_intervals, ref_labels, est_intervals, est_labels
    )
    durations = mir_eval.util.intervals_to_durations(merged)
    out = {
        "duration": float(ref_intervals.max() - ref_intervals.min()),
        "invalid_labels": est_labels.count("X"),
    }
    for name in ("majmin", "sevenths"):
        comparison = getattr(mir_eval.chord, name)(ref, est)
        out[name] = float(mir_eval.chord.weighted_accuracy(comparison, durations))
    return out


def tempo_scores(reference: float, estimate: float | None) -> dict:
    """Accuracy 1: within 4 %; accuracy 2: also counting double, half, triple and a third."""
    if not estimate:
        return {"tempo_acc1": 0.0, "tempo_acc2": 0.0}

    def close(factor: float) -> bool:
        return abs(estimate - reference * factor) <= 0.04 * reference * factor

    return {
        "tempo_acc1": float(close(1)),
        "tempo_acc2": float(any(close(f) for f in (1, 2, 0.5, 3, 1 / 3))),
    }


def evaluate(dataset: str, track: Track, result: dict) -> dict:
    ref = track.reference
    scores: dict = {"track": track.id, "analysis_seconds": result["analysis_seconds"]}
    if ref.get("key"):
        estimate = _mir_eval_key(result["key"]["best"])
        score = mir_eval.key.weighted_score(ref["key"], estimate)
        scores |= {"key_ref": ref["key"], "key_est": estimate, "key_weighted": score}
        scores["key_category"] = KEY_CATEGORIES.get(score, "other")
    if dataset == "guitarset":
        scores["style"] = ref["style"]
        scores |= {f"leadsheet_{k}": v for k, v in chord_scores(ref["chords_leadsheet"], result).items()}
        scores |= {f"performed_{k}": v for k, v in chord_scores(ref["chords_performed"], result).items()}
        scores["beat_f"] = float(
            mir_eval.beat.f_measure(
                mir_eval.beat.trim_beats(np.array(ref["beats"])),
                mir_eval.beat.trim_beats(np.array(result["beats"])),
            )
        )
        scores |= tempo_scores(ref["tempo"], result["tempo"].get("bpm"))
        scores |= {"tempo_ref": ref["tempo"], "tempo_est": result["tempo"].get("bpm")}
    return scores


# ---------------------------------------------------------------- run


def analyze(track: Track, cache: Path) -> dict:
    """Tonos' report for the track, computed once and kept as JSON."""
    path = cache / f"{track.id}.json"
    if path.exists():
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("version") == pipeline.VERSION:
            return result
    result = pipeline.analyze(track.audio)
    path.write_text(json.dumps(result), encoding="utf-8")
    return result


def run(dataset: str, data_dir: Path, limit: int | None) -> list[dict]:
    tracks = TRACKS[dataset](data_dir / dataset)
    if not tracks:
        raise SystemExit(f"No tracks found in {data_dir / dataset}: use --download")
    tracks = tracks[:limit] if limit else tracks
    cache = data_dir / "results" / dataset
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    start = time.perf_counter()
    for i, track in enumerate(tracks, 1):
        try:
            rows.append(evaluate(dataset, track, analyze(track, cache)))
        except Exception as e:  # one broken file must not stop a run of hours
            print(f"\n{track.id}: {e}", file=sys.stderr)
            rows.append({"track": track.id, "error": str(e)})
        elapsed = time.perf_counter() - start
        print(f"\r{dataset}: {i}/{len(tracks)} ({elapsed / i:.1f} s per track)", end="", flush=True)
    print()
    return rows


# ---------------------------------------------------------------- report


def _mean(rows: list[dict], key: str, weight: str | None = None) -> float:
    values = [(r[key], r[weight] if weight else 1.0) for r in rows if key in r]
    total = sum(w for _, w in values)
    return sum(v * w for v, w in values) / total if total else float("nan")


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %"


def summary(dataset: str, rows: list[dict]) -> list[str]:
    ok = [r for r in rows if "error" not in r]
    errors = len(rows) - len(ok)
    lines = []
    if dataset == "giantsteps_key":
        counts = {c: sum(r["key_category"] == c for r in ok) for c in KEY_CATEGORIES.values()}
        lines += [
            "| Metric | Value |",
            "|---|---|",
            f"| Tracks analyzed | {len(ok)} (failed: {errors}) |",
            f"| Weighted key score (MIREX) | **{_pct(_mean(ok, 'key_weighted'))}** |",
        ]
        lines += [f"| {c.capitalize()} | {_pct(n / len(ok))} ({n}) |" for c, n in counts.items()]
        skipped = SKIPPED.get(dataset, Counter())
        if skipped:
            reasons = ", ".join(f"{n} {why}" for why, n in skipped.most_common())
            lines.append(
                f"\nLeft out, because of their annotation: {sum(skipped.values())} excerpts ({reasons})."
            )
        return lines
    comp = [r for r in ok if r["style"] == "comp"]
    lines += [
        "| Metric | All tracks | Comping only |",
        "|---|---|---|",
        f"| Tracks analyzed | {len(ok)} (failed: {errors}) | {len(comp)} |",
    ]
    for label, key, weight in [
        ("Chords, major/minor (vs. lead sheet)", "leadsheet_majmin", "leadsheet_duration"),
        ("Chords, sevenths (vs. lead sheet)", "leadsheet_sevenths", "leadsheet_duration"),
        ("Chords, major/minor (vs. what was played)", "performed_majmin", "performed_duration"),
        ("Chords, sevenths (vs. what was played)", "performed_sevenths", "performed_duration"),
        ("Beats, F-measure", "beat_f", None),
        ("Tempo within 4 %", "tempo_acc1", None),
        ("Tempo within 4 %, also counting double, half, triple, a third", "tempo_acc2", None),
        ("Key, weighted score", "key_weighted", None),
    ]:
        lines.append(f"| {label} | **{_pct(_mean(ok, key, weight))}** | {_pct(_mean(comp, key, weight))} |")
    invalid = sum(r.get("leadsheet_invalid_labels", 0) for r in ok)
    if invalid:
        lines.append(f"\n{invalid} chord labels of Tonos were not valid for mir_eval and were ignored.")
    # Chords on the comping tracks, style by style: the styles differ a lot
    lines += [
        "",
        "Chords on the comping tracks, by style (major/minor, against the lead sheet):",
        "",
        "| Style | Tracks | Major/minor | Sevenths |",
        "|---|---|---|---|",
    ]
    for prefix, style in STYLES.items():
        rows_of_style = [r for r in comp if r["track"].split("_")[1].startswith(prefix)]
        majmin = _mean(rows_of_style, "leadsheet_majmin", "leadsheet_duration")
        sevenths = _mean(rows_of_style, "leadsheet_sevenths", "leadsheet_duration")
        lines.append(f"| {style} | {len(rows_of_style)} | {_pct(majmin)} | {_pct(sevenths)} |")
    return lines


def write_csv(dataset: str, rows: list[dict]) -> None:
    out = HERE / "results" / f"{dataset}.csv"
    out.parent.mkdir(exist_ok=True)
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k != "track", k))
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: f"{v:.4f}" if isinstance(v, float) else v for k, v in row.items()})


def write_results(sections: dict[str, list[str]], rows: list[dict]) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    body = []
    for dataset, lines in sections.items():
        info = DATASETS[dataset]
        body += [f"### {info.title}", "", f"[{info.source}]({info.source}), {info.license}.", "", *lines, ""]
    seconds = [r["analysis_seconds"] for r in rows if "analysis_seconds" in r]
    text = RESULTS.format(
        date=datetime.date.today().isoformat(),
        version=__version__,
        analysis_version=pipeline.VERSION,
        commit=commit or "unknown",
        hours=f"{sum(seconds) / 3600:.1f}",
        per_track=f"{np.mean(seconds):.1f}",
        machine=f"{platform.processor() or platform.machine()}, {os.cpu_count()} threads",
        results="\n".join(body).strip(),
    )
    (HERE / "results.md").write_text(text, encoding="utf-8")


RESULTS = """# Benchmark

How accurate Tonos is on public datasets, measured with [mir_eval](https://github.com/mir-evaluation/mir_eval)
by [`benchmarks/run.py`](run.py). These numbers are written by the script: do not edit them by hand.

- **Date:** {date}
- **Tonos:** {version} (analysis version {analysis_version}, commit `{commit}`)
- **Analysis time:** {per_track} s per track on average, {hours} h in total ({machine})

## Results

{results}

## What the numbers mean

- **Weighted key score:** the MIREX score: 1 for the right key, 0.5 for a fifth away, 0.3 for the
  relative key, 0.2 for the parallel key, 0 otherwise.
- **Chords:** the share of the time in which Tonos' chord matches the reference, weighted by the
  length of each track. *Major/minor* compares only the root and whether the chord is major or
  minor. *Sevenths* also compares the seventh. GuitarSet has two references: the lead sheet the
  guitarist read, and the chords inferred from what was actually played.
- **Beats:** F-measure with a 70 ms window, ignoring the first 5 seconds (mir_eval's default).
- **Tempo:** the share of tracks whose tempo is within 4 % of the reference. The second line also
  accepts double, half, triple and a third of it, the usual errors.

## Caveats

- **The beat model has seen GuitarSet.** Beat This! (CPJKU, 2024) was trained on 16 datasets,
  GuitarSet among them, so its beat and tempo scores on GuitarSet are optimistic. Its authors
  kept GTZAN for testing; its audio is not openly licensed, so it is not used here.
- The chord model (Consonance-ACE) was trained on Isophonics and the McGill Billboard corpus,
  and the key model (S-KEY) learns without key labels, so GuitarSet and GiantSteps are new to
  them.
- **GuitarSet is solo guitar** (comping and solos), and **GiantSteps is electronic dance music.**
  Neither is a full band singing, the music Tonos meets most often; the results there can be
  better or worse.
- Comping tracks are the fairest test for chords: in the solos, the guitar plays melodies over
  chords that are only implied.

## Reproduce

```bash
python benchmarks/run.py --download
```

It downloads about 1.6 GB from Zenodo into `benchmarks/data/` (not committed), analyzes every
track (resuming if it is interrupted) and rewrites this file and the per-track scores in
`benchmarks/results/`.
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-dir", type=Path, default=HERE / "data", help="where the datasets are (or go)")
    p.add_argument("--dataset", choices=sorted(DATASETS), action="append", help="only these (default: all)")
    p.add_argument("--download", action="store_true", help="download the datasets that are missing")
    p.add_argument("--limit", type=int, help="only the first N tracks of each dataset (for a quick try)")
    args = p.parse_args()
    logging.disable(logging.INFO)

    datasets = args.dataset or list(DATASETS)
    if args.download:
        for name in datasets:
            download(DATASETS[name], args.data_dir / name)
    sections, all_rows = {}, []
    for name in datasets:
        rows = run(name, args.data_dir, args.limit)
        all_rows += rows
        sections[name] = summary(name, rows)
        print("\n".join(sections[name]))
        if not args.limit:
            write_csv(name, rows)
    if args.limit:
        print("\n(--limit: benchmarks/results.md and the CSV files were not updated)")
    else:
        write_results(sections, all_rows)
        print("\nWritten to benchmarks/results.md")


if __name__ == "__main__":
    main()
