"""Analizador musical.

    python -m app                 abre la app en el navegador
    python -m app cancion.mp4     analiza un archivo y muestra el resultado en la terminal
    python -m app cancion.mp4 --json
    python -m app --precargar     descarga y prueba los modelos (lo usa instalar.ps1)
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def _mmss(segundos: float) -> str:
    return f"{int(segundos // 60)}:{int(segundos % 60):02d}"


def _texto(r: dict) -> str:
    lineas = [f"Archivo: {r['archivo']['nombre']} ({_mmss(r['archivo']['duracion'])})", ""]

    t = r["tempo"]
    if t.get("bpm"):
        alt = t["alternativas"]
        lineas.append(f"Tempo:      {t['bpm']:.0f} BPM  (al doble o a la mitad: {alt['doble']:.0f} / {alt['mitad']:.0f})")
        if t["sugerencia"]:
            lineas.append(f"            probablemente lo sientas a {alt[t['sugerencia']]:.0f} BPM")
        if not t["estable"]:
            lineas.append(f"            el tempo varía entre {t['rango'][0]:.0f} y {t['rango'][1]:.0f} BPM")
    else:
        lineas.append(f"Tempo:      no determinado ({t.get('motivo')})")

    c = r["compas"]
    if c.get("lectura"):
        alt = f" ({c['alternativa']})" if c.get("alternativa") else ""
        lineas.append(f"Compás:     {c['lectura']}{alt}")
        if c.get("fuente") == "periodicidad":
            origen = f"la armonía y el bajo se repiten cada {c['pulsos_por_compas']} pulsos"
        else:
            origen = f"cuenta en {c['pulsos_por_compas']} en el {c['acuerdo'] * 100:.0f} % de los compases"
            if (c.get("segundo_metodo") or {}).get("confirma"):
                origen += " (y la armonía lo confirma)"
        lineas.append(f"            {origen}; subdivisión {c['subdivision']['tipo']}; confianza {c['confianza']}")
        for aviso in c.get("avisos", []):
            if aviso.startswith("El detector") or aviso.startswith("No se pudo determinar"):
                lineas.append(f"            {aviso}")
    else:
        lineas.append(f"Compás:     no determinado. {c.get('motivo', '')}")

    k = r["tonalidad"]
    p = k["principal"]
    lineas.append(f"Tonalidad:  {p['latino']} ({p['americano']}), confianza {k['confianza']}")
    alts = ", ".join(f"{a['latino']} ({a['motivo']})" for a in k["alternativas"])
    lineas.append(f"            alternativas: {alts}")
    for cambio in k["por_tramos"]["cambios"]:
        lineas.append(f"            posible cambio: {cambio['latino']} entre {_mmss(cambio['inicio'])} "
                      f"y {_mmss(cambio['fin'])}")
    if r["afinacion"]["aviso"]:
        lineas.append(f"            {r['afinacion']['aviso']}")

    resumen = r["acordes"]["resumen_simple"]
    if not resumen:
        lineas += ["", "Acordes:   no se detectaron acordes (¿solo percusión, voz hablada o ruido?)"]
    else:
        usados = ", ".join(f"{a['latino']} {a['proporcion'] * 100:.0f} %" for a in resumen[:8])
        lineas += ["", f"Acordes más usados: {usados}", "", "Primeros 16 compases:"]
        segs = r["acordes"]["segmentos"]
        celdas = []
        for comp in r["compases"][:16]:
            nombres = []
            for i in comp["acordes"]:
                n = segs[i]["latino_simple"]
                if not nombres or nombres[-1] != n:
                    nombres.append(n)
            celdas.append(f"{comp['etiqueta']}: {' '.join(nombres) or '—'}")
        for i in range(0, len(celdas), 4):
            lineas.append("| " + " | ".join(f"{c:<20}" for c in celdas[i:i + 4]) + " |")
    lineas += ["", f"(análisis en {r['segundos_de_analisis']:.0f} s)"]
    return "\n".join(lineas)


def _puerto_ocupado(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _silenciar_logs() -> None:
    import logging

    logging.disable(logging.INFO)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    p = argparse.ArgumentParser(prog="python -m app", description="Analizador musical")
    p.add_argument("archivo", nargs="?", help="archivo a analizar en la terminal")
    p.add_argument("--json", action="store_true", help="mostrar el resultado completo en JSON")
    p.add_argument("--puerto", type=int, default=8765)
    p.add_argument("--no-abrir", action="store_true", help="no abrir el navegador")
    p.add_argument("--precargar", action="store_true", help="descargar y probar los modelos")
    a = p.parse_args()

    if a.precargar:
        _silenciar_logs()
        from .analisis import pipeline

        pipeline.precargar()
        print("Modelos listos.")
        return

    if a.archivo:
        _silenciar_logs()
        from .analisis import pipeline
        from .analisis.audio import ErrorDeAudio

        ruta = Path(a.archivo)
        if not ruta.is_file():
            sys.exit(f"No encuentro el archivo: {ruta}")

        def progreso(paso: str, fraccion: float) -> None:
            print(f"\r{fraccion * 100:3.0f} %  {paso:<50}", end="", file=sys.stderr, flush=True)

        try:
            resultado = pipeline.analizar(ruta, progreso)
        except ErrorDeAudio as e:
            sys.exit(f"\n{e}")
        print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
        print(json.dumps(resultado, ensure_ascii=False, indent=2) if a.json else _texto(resultado))
        return

    url = f"http://127.0.0.1:{a.puerto}"
    if _puerto_ocupado(a.puerto):
        # Ya hay una ventana abierta: no se arranca otra (borraría los archivos en cola)
        print(f"El analizador ya está abierto en {url}")
        if not a.no_abrir:
            webbrowser.open(url)
        return

    import uvicorn

    from .servidor import app

    if not a.no_abrir:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"Analizador musical abierto en {url}  (cerrá esta ventana o apretá Ctrl+C para salir)")
    uvicorn.run(app, host="127.0.0.1", port=a.puerto, log_level="warning")


if __name__ == "__main__":
    main()
