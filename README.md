# Analizador musical

Una app que corre en tu PC: le subís una canción o un video (MP4, MP3, M4A, WAV, FLAC, MKV…)
y te dice el **tempo**, el **compás**, la **tonalidad** y los **acordes** compás por compás.
Tiene un reproductor que te muestra el acorde que está sonando, y un clic opcional en cada pulso
para comprobar de oído si el análisis está bien.

Todo se procesa en tu computadora. No usa internet salvo para descargar los modelos la primera vez.

## Instalación (una sola vez)

Necesitás Python 3.12, ffmpeg y git (si falta alguno, `instalar.ps1` te dice cómo instalarlo).
Después, en una terminal dentro de esta carpeta, ejecutá:

```powershell
.\instalar.ps1
```

Tarda unos minutos y ocupa ~1,5 GB en `%LOCALAPPDATA%\analizador-musical\venv`.

## Uso

- **App web:** doble clic en `iniciar.bat`. Se abre el navegador en http://127.0.0.1:8765.
  Para apagarla, cerrá la ventana negra. Si ya estaba abierta, solo te abre el navegador.
  Podés soltar un archivo en cualquier parte de la página, incluso con un reporte abierto.
- **Terminal:** `iniciar.bat "C:\ruta\a\cancion.mp4"` muestra el reporte en texto.
  Con `--json` muestra todos los datos.

Un análisis tarda entre 10 y 30 segundos por canción. Si volvés a subir el mismo archivo,
el resultado sale al instante porque queda guardado.

## Qué tan confiable es

| Qué | Confiabilidad | Cómo se calcula |
|---|---|---|
| Tempo y pulsos | Alta en música con batería; el error típico es dar el doble o la mitad | Beat This! (CPJKU, 2024) más un segundo método de control (librosa) |
| Compás | Media en 3/4 y 4/4; detecta 5/4 y 7/4 cuando la armonía se repite con claridad | Se cuentan los pulsos entre primeros tiempos y se contrasta con cada cuántos pulsos se repiten la armonía y el bajo; además se mira si cada pulso se divide en 2 o en 3 |
| Tonalidad | Media: exacta en 7 u 8 de cada 10 canciones; si falla, suele ser la relativa o una quinta | S-KEY (Deezer, 2025) más un segundo método a partir de los acordes |
| Acordes | Media: ~78 % del tiempo en mayor/menor, menos con séptimas | Consonance-ACE (2025), un acorde por pulso |

Advertencias:

- **El 3/4 y el 6/8 no se pueden distinguir de forma automática.** En folklore (chacarera, zamba)
  se alternan a propósito.
- **Compases de 5 y 7:** el detector de primeros tiempos casi no los vio al entrenarse y los fuerza
  a 4. Por eso un segundo método mide cada cuántos pulsos se repite la armonía. Cuando no queda
  claro en qué pulso empieza cada compás, la grilla se marca como aproximada.
- **Los modelos se entrenaron sobre todo con pop y rock en inglés.** Folklore, tango y otros géneros
  latinos pueden dar peores resultados.
- **Se da una sola tonalidad por canción,** aunque la app avisa si detecta un tramo largo en otra.

## Pruebas

```powershell
& "$env:LOCALAPPDATA\analizador-musical\venv\Scripts\python.exe" -m pytest            # todas (~1 min)
& "$env:LOCALAPPDATA\analizador-musical\venv\Scripts\python.exe" -m pytest -m "not lento"  # solo las rápidas
```

Las pruebas lentas generan canciones sintéticas (pop en Sol a 120 BPM, vals en Re a 150 BPM),
las guardan como MP4 y comprueban tempo, compás, tonalidad y acordes.

En GitHub se corren solas en cada PR y en cada cambio a `main`
(workflow [Tests](.github/workflows/tests.yml), en Linux con Python 3.12).

## Dónde guarda cosas

- `%LOCALAPPDATA%\analizador-musical\venv`: el entorno de Python.
- `%LOCALAPPDATA%\analizador-musical\cache`: los análisis ya hechos (JSON chicos).
- `%USERPROFILE%\.cache\torch\hub\checkpoints\beat_this-final0.ckpt`: el modelo de pulsos (77 MB).

Para desinstalar, borrá esas tres cosas y esta carpeta.

## Licencias

Uso personal. El código de los tres modelos es MIT, pero los pesos de Consonance-ACE se entrenaron
con anotaciones de uso no comercial, y la licencia de los pesos de S-KEY no está declarada.
Antes de usar esto en un producto comercial, revisalo.

## Ideas para seguir

- **Secciones** (intro, estrofa, estribillo): SongFormer, que necesita Linux o WSL2 con placa NVIDIA.
- **Separar instrumentos:** Demucs (tarda ~6 min por canción sin placa de video).
- **Hacerle preguntas en lenguaje natural:** pasarle el JSON del análisis a Claude.
