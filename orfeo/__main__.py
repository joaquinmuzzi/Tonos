"""orfeo command line.

python -m orfeo                 opens the app in the browser
python -m orfeo song.mp4        analyzes a file and prints the result in the terminal
python -m orfeo song.mp4 --json
python -m orfeo --preload       downloads and tests the models (used by instalar.ps1)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from .messages import english, message

INDENT = " " * 8


def _mmss(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _key(k: dict) -> str:
    return f"{k['letter']} {k['mode']} ({k['solfege']} {k['mode']})"


def _bar_label(bar: dict) -> str:
    return bar["kind"] if bar["kind"] in ("pickup", "intro") else f"{bar['kind']} {bar['number']}"


def _tempo_lines(t: dict) -> list[str]:
    if not t.get("bpm"):
        return [f"Tempo:  unknown. {english(t['reason'])}"]
    alt = t["alternatives"]
    lines = [f"Tempo:  {t['bpm']:.0f} BPM  (counted double / half: {alt['double']:.0f} / {alt['half']:.0f})"]
    if t["suggestion"]:
        lines.append(f"{INDENT}you will probably feel it at {alt[t['suggestion']]:.0f} BPM")
    if not t["stable"]:
        lines.append(f"{INDENT}the tempo varies between {t['range'][0]:.0f} and {t['range'][1]:.0f} BPM")
    if t.get("warning"):
        lines.append(f"{INDENT}{english(t['warning'])}")
    return lines


def _meter_lines(m: dict) -> list[str]:
    if not m.get("beats_per_bar"):
        return [f"Meter:  unknown. {english(m['reason'])}"]
    reading = m["time_signature"] or f"{m['beats_per_bar']} beats per bar"
    if m["swing"]:
        reading += " swing"
    if m["alternative"]:
        reading += f" ({english(m['alternative'])})"
    if m["source"] == "periodicity":
        source = f"the harmony and the bass repeat every {m['beats_per_bar']} beats"
    else:
        source = f"counts {m['beats_per_bar']} in {m['agreement'] * 100:.0f} % of the bars"
        if (m.get("second_method") or {}).get("confirms"):
            source += " (and the harmony confirms it)"
    lines = [
        f"Meter:  {reading}",
        f"{INDENT}{source}; {m['subdivision']['kind']} subdivision; {m['confidence']} confidence",
    ]
    lines += [
        f"{INDENT}{english(w)}"
        for w in m["warnings"]
        if w["code"] in ("meter_from_harmony", "approximate_grid")
    ]
    return lines


def _key_lines(k: dict, tuning: dict) -> list[str]:
    reasons = {"relative": "relative key", "runner_up": "the model's second choice"}
    alternatives = ", ".join(f"{_key(a)} ({reasons[a['reason']]})" for a in k["alternatives"])
    lines = [
        f"Key:    {_key(k['best'])}, {k['confidence']} confidence",
        f"{INDENT}also possible: {alternatives}",
    ]
    for change in k["sections"]["changes"]:
        lines.append(
            f"{INDENT}possible change to {_key(change)} between {_mmss(change['start'])} "
            f"and {_mmss(change['end'])}"
        )
    if tuning["warning"]:
        lines.append(f"{INDENT}{english(tuning['warning'])}")
    return lines


def _chord_lines(r: dict) -> list[str]:
    summary = r["chords"]["summary_simple"]
    if not summary:
        return ["Chords: none detected (percussion only, speech or noise?)"]
    used = ", ".join(f"{a['letter']} {a['share'] * 100:.0f} %" for a in summary[:8])
    lines = [f"Most used chords: {used}", "", "First 16 bars:"]
    segments = r["chords"]["segments"]
    cells = []
    for bar in r["bars"][:16]:
        names = []
        for i in bar["chords"]:
            name = segments[i]["letter_simple"]
            if not names or names[-1] != name:
                names.append(name)
        cells.append(f"{_bar_label(bar)}: {' '.join(names) or '—'}")
    for i in range(0, len(cells), 4):
        lines.append("| " + " | ".join(f"{c:<20}" for c in cells[i : i + 4]) + " |")
    return lines


def _text_report(r: dict) -> str:
    lines = [f"File:   {r['file']['name']} ({_mmss(r['file']['duration'])})", ""]
    lines += _tempo_lines(r["tempo"])
    lines += _meter_lines(r["meter"])
    lines += _key_lines(r["key"], r["tuning"])
    lines += ["", *_chord_lines(r)]
    lines += ["", f"(analyzed in {r['analysis_seconds']:.0f} s)"]
    return "\n".join(lines)


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _silence_logs() -> None:
    import logging

    logging.disable(logging.INFO)


def main() -> None:
    with contextlib.suppress(AttributeError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="python -m orfeo", description="Find the tempo, meter, key and chords of a song."
    )
    p.add_argument("file", nargs="?", help="file to analyze in the terminal (without it, opens the app)")
    p.add_argument("--json", action="store_true", help="print the full result as JSON")
    p.add_argument("--port", type=int, default=8765, help="port of the local web app (default: 8765)")
    p.add_argument("--no-browser", action="store_true", help="do not open the browser")
    p.add_argument("--preload", action="store_true", help="download and test the models")
    args = p.parse_args()

    if args.preload:
        _silence_logs()
        from .analysis import pipeline

        pipeline.preload()
        print("Models ready.")
        return

    if args.file:
        _silence_logs()
        from .analysis import pipeline
        from .analysis.audio import AudioError

        path = Path(args.file)
        if not path.is_file():
            sys.exit(f"File not found: {path}")

        def progress(step: str, fraction: float) -> None:
            text = english(message(step))
            print(f"\r{fraction * 100:3.0f} %  {text:<50}", end="", file=sys.stderr, flush=True)

        try:
            result = pipeline.analyze(path, progress)
        except AudioError as e:
            sys.exit(f"\n{e}")
        print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else _text_report(result))
        return

    url = f"http://127.0.0.1:{args.port}"
    if _port_in_use(args.port):
        # The app is already running: do not start another one (it would delete the queued files)
        print(f"orfeo is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    import uvicorn

    from .server import app

    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"orfeo is running at {url}  (close this window or press Ctrl+C to quit)")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
