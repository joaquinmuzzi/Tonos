# JSON report format

The command-line interface prints the complete analysis report when it is called with
`--json`:

```console
tonos.bat path/to/song.mp3 --json
./tonos.sh path/to/song.mp3 --json
```

The JSON is the object returned by the analysis pipeline. Times are seconds from the start of
the first audio track that was analyzed. Numbers are rounded for display unless noted otherwise.
The report is intended for clients that want to render the analysis, rather than as a promise that
every analysis is certain: confidence and warning fields describe cases where the detectors had
less evidence.

## Versioning and caching

`version` is the report-format version. It changes whenever the report's structure or analysis
meaning changes, and is also the cache invalidation key. A client should not reuse a cached report
under a different `version`.

`tonos_version` is the installed Tonos application version. It identifies the producer, but
`version` is the field to use when deciding whether a cached report is compatible.

## Top-level object

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `version` | integer | no | Report-format and cache version. |
| `tonos_version` | string | no | Tonos version that produced the report. |
| `file` | object | no | Basic information about the analyzed media file. |
| `tempo` | object | no | Tempo estimate and tempo-related diagnostics. |
| `meter` | object | no | Meter estimate and bar-grid diagnostics. |
| `key` | object | no | Global key, alternatives, and possible key changes. |
| `tuning` | object | no | Deviation from standard A = 440 Hz tuning. |
| `chords` | object | no | Chord segments and summaries. |
| `bars` | array of objects | no | The bar/section grid and chord indices for each cell. |
| `beats` | array of numbers (seconds) | no | Beat positions used by the report. It can be empty when no usable beat grid was found. |
| `downbeats` | array of numbers (seconds) | no | Bar-start positions. It can be empty when downbeats were not reliable enough. |
| `analysis_seconds` | number (seconds) | no | Wall-clock time used to produce the report. |

## `file`

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `name` | string | no | Input file name. |
| `duration` | number (seconds) | no | Duration of the selected audio track. |
| `audio_track` | integer | no | One-based index of the audio track used for analysis. |

## `tempo`

The object always contains `unified_beats`, which records beat corrections made while building the
final grid. When at least eight beats are available, it also contains the tempo estimate and the
following diagnostics:

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `bpm` | number (beats/minute) | yes | Main tempo estimate. It is `null` when there are too few beats. |
| `confidence` | `"low"`, `"medium"`, or `"high"` | conditional | Confidence in the tempo estimate; omitted when `bpm` is unavailable. |
| `alternatives` | object | conditional | `half` and `double` are the half- and double-time readings in BPM. |
| `suggestion` | `"half"`, `"double"`, or `null` | conditional | A likely double-/half-time interpretation when the estimate is outside the usual range. |
| `range` | two-number array (BPM) | conditional | 10th–90th percentile of local tempo estimates. |
| `stable` | boolean | conditional | Whether local tempo variation is below the stability threshold. |
| `regularity` | number from 0 to 1 | conditional | Share of beat intervals close to the typical interval. |
| `curve` | array of `[time, bpm]` pairs | conditional | Local BPM samples across the song. |
| `second_method` | object | conditional | Independent onset-envelope estimate: `bpm` and `relation` (`same`, `double`, `half`, `triple`, `third`, or `null`). |
| `unified_beats` | object | no | Beat-grid corrections: `removed` extra beats and `added` missing beats. Always present, including when `bpm` is `null`. |
| `warning` | message object or `null` | yes | A tempo warning, for example when the beat grid was corrected or retracked. |

If there are too few beats, the object instead has `bpm: null` and a `reason` message; the
estimate-only fields are omitted. Consumers should check `bpm` before reading them.

## `meter`

If the meter cannot be estimated, the result contains `reason` and the fields that depend on a
counted meter are omitted.

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `beats_per_bar` | integer | yes | Number of beats in the chosen bar. `null` when no meter could be estimated. |
| `time_signature` | string | yes | Display signature such as `4/4`; `null` for an unknown or unusual reading. |
| `swing` | boolean | no | Whether a ternary subdivision is represented as swing/shuffle. |
| `alternative` | message object or `null` | yes | Alternative reading such as 12/8, an odd-meter spelling, or shuffle. |
| `source` | `"downbeats"`, `"periodicity"`, or `null` | yes | Whether the meter came from detected downbeats or harmonic repetition. |
| `agreement` | number from 0 to 1 | conditional | Share of counted bars with the modal beat count. It is `0` when no bars were countable. |
| `confidence` | `"low"`, `"medium"`, or `"high"` | no | Confidence in the meter estimate. |
| `bars_counted` | integer | conditional | Number of complete bars used to count the meter. |
| `downbeat_count` | integer | conditional | Most common number of beats between downbeats. |
| `distribution` | object of string integers to numbers | conditional | Share of counted bars for each observed bar length, for example `{ "4": 1.0 }`. |
| `subdivision` | object | no | `kind` is `binary`, `ternary`, or `unclear`; `ratio` is the ternary/binary onset-strength ratio, or `null`. |
| `second_method` | object or `null` | yes | Harmonic-periodicity comparison. It can contain `beats`, `scores`, `confirms`, `replaces`, `contradicts`, and `strong`. |
| `warnings` | array of message objects | no | Meter warnings, including inconsistent bars or an approximate grid. |
| `approximate_grid` | boolean | conditional | Whether bar starts are approximate because harmonic periodicity could not determine an exact phase. Present when the meter source is `"periodicity"`. |
| `regrouped_bars` | integer | conditional | Number of bars repaired after regularizing detected downbeats. Present for downbeat-based meter. |

## `key`

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `best` | object | no | Best global key: `tonic_pc` (pitch class 0–11), `mode` (`major`/`minor`), `probability`, `solfege`, `letter`, and `scale` (both seven-note name arrays). |
| `confidence` | `"low"`, `"medium"`, or `"high"` | no | Confidence after comparing the model with the chord-based method. |
| `advantage` | positive number | no | How many times more likely the best model result is than the second result. |
| `alternatives` | array of objects | no | Other plausible keys. Each has the same key fields as `best` except `scale`, plus `reason` (`relative` or `runner_up`). |
| `sections` | object | no | Possible key changes: `windows`, `agreement`, and `changes`. A window has start/end seconds, key names, pitch class, mode, and probability. A change has start/end and the changed key. |
| `second_method` | object or `null` | yes | Chord-derived key comparison with `agreement`, `tonic_pc`, `mode`, `solfege`, and `letter`. `null` means no chord key was available. |

`tonic_pc` uses the chromatic pitch-class numbering `C = 0`, `C♯/D♭ = 1`, …, `B = 11`.

## `tuning`

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `cents` | integer (cents) | no | Deviation from A = 440 Hz; positive is sharp and negative is flat. |
| `warning` | message object or `null` | yes | Warning when the deviation is large enough that key/chord names may be a semitone off. |

## `chords`

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `segments` | array of objects | no | Consecutive chord segments. A bar refers to these objects by index. |
| `summary` | array of `{solfege, letter, share}` objects | no | Most-used full chord names, ranked by sounding time. `share` is from 0 to 1. |
| `summary_simple` | array of `{solfege, letter, share}` objects | no | The same summary using major/minor-only names. |

Each `segments` object contains:

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `start`, `end` | numbers (seconds) | no | Segment boundaries. |
| `label` | string | no | Original Harte chord label. |
| `is_chord` | boolean | no | `false` for no-chord/noise segments. |
| `root_pc` | integer 0–11 or `null` | yes | Root pitch class, when a chord is present. |
| `description` | string | no | Human-readable chord description, or `no chord`. |
| `solfege`, `letter` | strings | no | Full chord name in solfège or letter notation. `—` means no chord. |
| `solfege_simple`, `letter_simple` | strings | no | Major/minor-only chord name, or `—`. |

## `bars`

Each element is a display cell, not a second analysis of the audio:

| Key | Type / unit | Nullable | Meaning |
| --- | --- | --- | --- |
| `number` | integer | no | Bar number. `0` is reserved for an intro or pickup. |
| `kind` | `bar`, `section`, `intro`, or `pickup` | no | Why the cell exists. `section` is used when reliable downbeats are unavailable. |
| `start`, `end` | numbers (seconds) | no | Cell boundaries. |
| `chords` | array of integers | no | Zero-based indices into `chords.segments`, in time order. |

## `beats` and `downbeats`

Both arrays contain monotonically increasing timestamps in seconds. `beats` is the final unified
beat grid used by tempo and chord display. `downbeats` contains the subset that starts bars. Either
array may be empty when the corresponding detector cannot provide a reliable result; the report
still contains a `bars` array using fallback sections when possible.

## Message objects

Warnings, reasons, and alternative readings are deliberately not localized strings. They use this
shape so each interface can translate them independently:

```json
{
  "code": "beats_corrected",
  "params": {"count": 4}
}
```

The English templates are in [`tonos/messages.py`](../tonos/messages.py). The message codes that
can occur in a JSON report are:

| Code | Used for |
| --- | --- |
| `too_few_beats` | `tempo.reason` when tempo cannot be estimated. |
| `beats_corrected` | `tempo.warning` after extra/missed beats are corrected. |
| `beats_retracked` | `tempo.warning` after a steady beat grid is re-estimated. |
| `too_few_downbeats` | `meter.reason` when there are too few bar starts. |
| `all_beats_downbeats` | `meter.reason` when almost every beat is marked as a downbeat. |
| `meter_from_harmony`, `meter_from_harmony_only` | `meter.warnings` when harmonic repetition chooses the meter. |
| `harmony_suggests` | `meter.warnings` when harmonic repetition disagrees with counted bars. |
| `inconsistent_bars` | `meter.warnings` when bar lengths vary. |
| `ternary_ambiguity`, `approximate_grid` | `meter.warnings` for known interpretation limits. |
| `or`, `or_either`, `or_counted_faster`, `or_with_triplets`, `or_shuffle`, `or_odd_meter`, `unusual_meter` | `meter.alternative` readings. |
| `tuning_sharp`, `tuning_flat` | `tuning.warning`. |

Codes not listed here are used by the web/server progress and error messages, not as fields in a
successful analysis report.

## Reading chords bar by bar

The bar's `chords` values are indices, so resolve them through `chords.segments`:

```python
import json
from pathlib import Path

report = json.loads(Path("demo/carefree.json").read_text(encoding="utf-8"))
segments = report["chords"]["segments"]

for bar in report["bars"]:
    names = [segments[index]["letter"] for index in bar["chords"]]
    print(f"{bar['number']:>3}: {' '.join(names) or '—'}")
```

This also works with a file produced by `tonos --json`; the checked-in demo is used here so the
example can be run without downloading the analysis models.
