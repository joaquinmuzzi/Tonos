# Benchmark

How accurate Tonos is on public datasets, measured with [mir_eval](https://github.com/mir-evaluation/mir_eval)
by [`benchmarks/run.py`](run.py). These numbers are written by the script: do not edit them by hand.

- **Date:** 2026-10-13
- **Tonos:** 0.2.0 (analysis version 12, commit `09bd4cc`)
- **Analysis time:** 7.9 s per track on average, 2.0 h in total (AMD64 Family 25 Model 33 Stepping 2, AuthenticAMD, 12 threads)

## Results

### GuitarSet

[https://zenodo.org/records/3371780](https://zenodo.org/records/3371780), CC BY 4.0.

| Metric | All tracks | Comping only |
|---|---|---|
| Tracks analyzed | 360 (failed: 0) | 180 |
| Chords, major/minor (vs. lead sheet) | **33.0 %** | 60.8 % |
| Chords, sevenths (vs. lead sheet) | **24.0 %** | 44.6 % |
| Chords, major/minor (vs. what was played) | **34.5 %** | 63.8 % |
| Chords, sevenths (vs. what was played) | **27.6 %** | 52.1 % |
| Beats, F-measure | **79.2 %** | 95.9 % |
| Tempo within 4 % | **76.4 %** | 90.6 % |
| Tempo within 4 %, also counting double, half, triple, a third | **92.8 %** | 100.0 % |
| Key, weighted score | **67.2 %** | 74.8 % |

Chords on the comping tracks, by style (major/minor, against the lead sheet):

| Style | Tracks | Major/minor | Sevenths |
|---|---|---|---|
| Bossa nova | 36 | 56.6 % | 31.2 % |
| Funk | 36 | 34.5 % | 20.9 % |
| Jazz | 36 | 48.4 % | 27.3 % |
| Rock | 36 | 79.9 % | 66.3 % |
| Singer-songwriter | 36 | 78.1 % | 66.4 % |

### GiantSteps+ EDM Key

[https://zenodo.org/records/1095691](https://zenodo.org/records/1095691), CC BY-SA 4.0.

| Metric | Value |
|---|---|
| Tracks analyzed | 566 (failed: 0) |
| Weighted key score (MIREX) | **75.8 %** |
| Correct | 70.7 % (400) |
| Fifth | 4.8 % (27) |
| Relative | 4.2 % (24) |
| Parallel | 7.2 % (41) |
| Other | 13.1 % (74) |

Left out, because of their annotation: 34 excerpts (28 neither major nor minor, 3 no key, 3 not a valid key name).

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
