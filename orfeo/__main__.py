"""orfeo command line.

python -m orfeo                 opens the app in the browser
python -m orfeo song.mp4        analyzes a file and prints the result in the terminal
python -m orfeo song.mp4 --json
python -m orfeo --precargar     downloads and tests the models (used by instalar.ps1)
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


def _mmss(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _text_report(r: dict) -> str:
    lines = [f"Archivo: {r['archivo']['nombre']} ({_mmss(r['archivo']['duracion'])})", ""]

    t = r["tempo"]
    if t.get("bpm"):
        alt = t["alternativas"]
        lines.append(
            f"Tempo:      {t['bpm']:.0f} BPM  (al doble o a la mitad: {alt['doble']:.0f} / {alt['mitad']:.0f})"
        )
        if t["sugerencia"]:
            lines.append(f"            probablemente lo sientas a {alt[t['sugerencia']]:.0f} BPM")
        if not t["estable"]:
            lines.append(f"            el tempo varía entre {t['rango'][0]:.0f} y {t['rango'][1]:.0f} BPM")
        if t.get("aviso"):
            lines.append(f"            {t['aviso']}")
    else:
        lines.append(f"Tempo:      no determinado ({t.get('motivo')})")

    c = r["compas"]
    if c.get("lectura"):
        alt = f" ({c['alternativa']})" if c.get("alternativa") else ""
        lines.append(f"Compás:     {c['lectura']}{alt}")
        if c.get("fuente") == "periodicidad":
            source_text = f"la armonía y el bajo se repiten cada {c['pulsos_por_compas']} pulsos"
        else:
            source_text = (
                f"cuenta en {c['pulsos_por_compas']} en el {c['acuerdo'] * 100:.0f} % de los compases"
            )
            if (c.get("segundo_metodo") or {}).get("confirma"):
                source_text += " (y la armonía lo confirma)"
        lines.append(
            f"            {source_text}; subdivisión {c['subdivision']['tipo']}; confianza {c['confianza']}"
        )
        for warning in c.get("avisos", []):
            if warning.startswith("El detector") or warning.startswith("No se pudo determinar"):
                lines.append(f"            {warning}")
    else:
        lines.append(f"Compás:     no determinado. {c.get('motivo', '')}")

    k = r["tonalidad"]
    p = k["principal"]
    lines.append(f"Tonalidad:  {p['latino']} ({p['americano']}), confianza {k['confianza']}")
    alts = ", ".join(f"{a['latino']} ({a['motivo']})" for a in k["alternativas"])
    lines.append(f"            alternativas: {alts}")
    for change in k["por_tramos"]["cambios"]:
        lines.append(
            f"            posible cambio: {change['latino']} entre {_mmss(change['inicio'])} "
            f"y {_mmss(change['fin'])}"
        )
    if r["afinacion"]["aviso"]:
        lines.append(f"            {r['afinacion']['aviso']}")

    summary = r["acordes"]["resumen_simple"]
    if not summary:
        lines += ["", "Acordes:   no se detectaron acordes (¿solo percusión, voz hablada o ruido?)"]
    else:
        used = ", ".join(f"{a['latino']} {a['proporcion'] * 100:.0f} %" for a in summary[:8])
        lines += ["", f"Acordes más usados: {used}", "", "Primeros 16 compases:"]
        segs = r["acordes"]["segmentos"]
        cells = []
        for bar in r["compases"][:16]:
            names = []
            for i in bar["acordes"]:
                n = segs[i]["latino_simple"]
                if not names or names[-1] != n:
                    names.append(n)
            cells.append(f"{bar['etiqueta']}: {' '.join(names) or '—'}")
        for i in range(0, len(cells), 4):
            lines.append("| " + " | ".join(f"{c:<20}" for c in cells[i : i + 4]) + " |")
    lines += ["", f"(análisis en {r['segundos_de_analisis']:.0f} s)"]
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

    p = argparse.ArgumentParser(prog="python -m orfeo", description="Analizador musical")
    p.add_argument("archivo", nargs="?", help="archivo a analizar en la terminal")
    p.add_argument("--json", action="store_true", help="mostrar el resultado completo en JSON")
    p.add_argument("--puerto", type=int, default=8765)
    p.add_argument("--no-abrir", action="store_true", help="no abrir el navegador")
    p.add_argument("--precargar", action="store_true", help="descargar y probar los modelos")
    a = p.parse_args()

    if a.precargar:
        _silence_logs()
        from .analysis import pipeline

        pipeline.preload()
        print("Modelos listos.")
        return

    if a.archivo:
        _silence_logs()
        from .analysis import pipeline
        from .analysis.audio import AudioError

        path = Path(a.archivo)
        if not path.is_file():
            sys.exit(f"No encuentro el archivo: {path}")

        def progress(step: str, fraction: float) -> None:
            print(f"\r{fraction * 100:3.0f} %  {step:<50}", end="", file=sys.stderr, flush=True)

        try:
            result = pipeline.analyze(path, progress)
        except AudioError as e:
            sys.exit(f"\n{e}")
        print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=2) if a.json else _text_report(result))
        return

    url = f"http://127.0.0.1:{a.puerto}"
    if _port_in_use(a.puerto):
        # The app is already running: do not start another one (it would delete the queued files)
        print(f"El analizador ya está abierto en {url}")
        if not a.no_abrir:
            webbrowser.open(url)
        return

    import uvicorn

    from .server import app

    if not a.no_abrir:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"Analizador musical abierto en {url}  (cerrá esta ventana o apretá Ctrl+C para salir)")
    uvicorn.run(app, host="127.0.0.1", port=a.puerto, log_level="warning")


if __name__ == "__main__":
    main()
