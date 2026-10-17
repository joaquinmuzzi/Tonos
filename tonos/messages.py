"""User-facing messages.

The analysis never returns finished sentences. It returns a message code and its parameters,
for example ``{"code": "too_long", "params": {"minutes": 20}}``, so that each interface can
show it in the reader's language: the web page has its own translations (``web/i18n.js``),
and the command line uses the English text below.
"""

from __future__ import annotations

Message = dict  # {"code": str, "params": dict}

ENGLISH = {
    # Reading the file
    "ffmpeg_missing": (
        "ffmpeg was not found. Install it (on Windows: winget install Gyan.FFmpeg) and open the "
        "terminal again."
    ),
    "no_audio_track": "The file has no audio track.",
    "drm_protected": "The file is DRM-protected and cannot be read.",
    "not_media": "Could not read the file: it does not look like valid audio or video.",
    "ffmpeg_failed": "ffmpeg could not read the file: {detail}",
    "too_short": "The audio is shorter than {seconds} seconds: too short to analyze.",
    "too_long": (
        "The audio is longer than {minutes} minutes, which is the maximum (for long mixes, cut "
        "out the song you are interested in)."
    ),
    "silent": "The audio is silent.",
    "all_tracks_silent": "All {tracks} audio tracks of the file are silent.",
    # Server
    "too_large": "The file is too large (maximum {gigabytes} GB).",
    "save_failed": "Could not save the file to disk: {detail}",
    "empty_file": "The file is empty.",
    "unexpected_error": "Unexpected error during the analysis: {detail}",
    "job_not_found": "That analysis does not exist (was the server restarted?).",
    # Progress steps
    "queued": "Waiting",
    "loading_models": "Loading the models (the first time takes a while)",
    "extracting_audio": "Extracting the audio",
    "finding_beats": "Finding the beats and downbeats",
    "tempo_and_meter": "Computing the tempo and the meter",
    "finding_key": "Finding the key",
    "recognizing_chords": "Recognizing the chords",
    "locating_bars": "Locating the bars",
    "building_report": "Building the report",
    "separating_tracks": "Separating the tracks",
    "separation_cancelled": "The separation was cancelled.",
    "done": "Done",
    # Tempo
    "too_few_beats": "Too few beats were detected to estimate the tempo.",
    "beats_corrected": (
        "In some stretches the detector marked extra beats (double time) or missed some: {count} "
        "beats were corrected so that the grid is even and the bars can be counted."
    ),
    "beats_retracked": (
        "The beat detector could not follow a steady beat (a single instrument, pauses or a free "
        "tempo), so the beat was estimated again at a steady tempo: the one at which the harmony "
        "repeats most clearly. Check it with the click."
    ),
    # Meter
    "too_few_downbeats": "Not enough downbeats were detected to estimate the meter.",
    "all_beats_downbeats": (
        "Almost every detected beat was marked as a downbeat, so the meter could not be counted. "
        "This happens with very free music or a lot of rubato."
    ),
    "meter_from_harmony": (
        "The downbeat detector marked bars of {counted} beats, but the harmony and the bass repeat "
        "every {beats} beats: the meter is most likely in {beats}. Automatic detectors were trained "
        "almost only on 4/4 music and tend to force it."
    ),
    "meter_from_harmony_only": (
        "The detected downbeats were not enough to count the meter, but the harmony and the bass "
        "repeat every {beats} beats."
    ),
    "harmony_suggests": (
        "A second method (how often the harmony repeats) suggests bars of {beats} beats: listen "
        "with the click on to decide."
    ),
    "inconsistent_bars": (
        "The detected bars do not always have the same number of beats: the meter may change "
        "during the song, or the downbeats may be misplaced."
    ),
    "ternary_ambiguity": (
        "3/4 and 6/8 are very easy to confuse (and some styles, like the chacarera or the zamba, "
        "alternate them on purpose). No automatic tool tells them apart well: listen to whether "
        "the beat you tap with your foot divides into 2 or into 3."
    ),
    "approximate_grid": (
        "Could not determine reliably on which beat each bar starts: the bar grid is approximate "
        "(it may be shifted by a few beats)."
    ),
    # Alternative readings of a meter
    "or": "or {signature}",
    "or_either": "or {first}, or {second}",
    "or_counted_faster": "or {signature} counted faster",
    "or_with_triplets": "or {signature} with triplets",
    "or_shuffle": "or shuffle; it can also be written in 12/8",
    "or_odd_meter": "or {signature} (odd meter)",
    "unusual_meter": "an unusual meter: take it with a grain of salt",
    # Tuning
    "tuning_sharp": (
        "The recording is {cents} cents sharp of standard tuning (A = 440 Hz). With such a "
        "deviation, the key and the chords may come out a semitone off."
    ),
    "tuning_flat": (
        "The recording is {cents} cents flat of standard tuning (A = 440 Hz). With such a "
        "deviation, the key and the chords may come out a semitone off."
    ),
}


def message(code: str, **params) -> Message:
    if code not in ENGLISH:
        raise KeyError(f"unknown message code: {code}")
    return {"code": code, "params": params}


def english(msg: Message) -> str:
    return ENGLISH[msg["code"]].format(**msg["params"])
