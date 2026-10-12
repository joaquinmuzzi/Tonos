"use strict";

/*
 * Texts of the interface, by language. The analysis does not return finished sentences but
 * message codes with parameters (see orfeo/messages.py); their translations live here too.
 * "{name}" is replaced by the parameter with that name.
 */
const MESSAGES = {
  es: {
    // Confidence badges
    confidence_high: "Confianza alta",
    confidence_medium: "Confianza media",
    confidence_low: "Confianza baja",

    // Upload and progress
    too_large_client:
      "El archivo es demasiado grande (máximo 1 GB). Si es un video, probá con una versión más liviana o solo con el audio.",
    uploading: "Subiendo el archivo…",
    uploading_percent: "Subiendo el archivo… {percent}",
    server_error: "El servidor respondió con un error ({status}).",
    connection_failed: "No me pude conectar con el analizador. ¿Sigue abierta su ventana?",
    connection_lost: "Perdí la conexión con el analizador: {detail}",

    // Tempo card
    tempo_title: "Tempo",
    tempo_suggestion: "Probablemente lo sientas a {bpm} BPM.",
    tempo_double_half: "Si lo contás al doble o a la mitad: {double} o {half} BPM.",
    tempo_stable: "Tempo estable.",
    tempo_varies: "El tempo varía entre {min} y {max} BPM.",
    tempo_irregular: "El pulso es irregular (tempo libre o rubato): tomá el número como aproximado.",
    tempo_same: "Un segundo método independiente da casi lo mismo ({bpm} BPM).",
    tempo_double: "Un segundo método da {bpm} BPM (el doble): es la ambigüedad típica del tempo.",
    tempo_half: "Un segundo método da {bpm} BPM (la mitad): es la ambigüedad típica del tempo.",
    tempo_triple: "Un segundo método da {bpm} BPM (el triple): suele pasar cuando el pulso se divide en tres.",
    tempo_third: "Un segundo método da {bpm} BPM (un tercio): suele pasar cuando el pulso se divide en tres.",
    tempo_mismatch: "Un segundo método da {bpm} BPM, que no coincide: tomá el tempo con cuidado.",
    tempo_curve_title: "Tempo a lo largo de la canción:",
    tempo_curve_label: "Tempo a lo largo de la canción, entre {min} y {max} BPM",

    // Meter card
    meter_title: "Compás",
    meter_swing: "{signature} con swing",
    meter_beats_per_bar: "{beats} pulsos por compás",
    meter_source_periodicity: "Cuenta en {beats}: la armonía y el bajo se repiten cada {beats} pulsos (o múltiplos).",
    meter_source_downbeats: "Cuenta en {beats}: así cuentan el {percent} de los {bars} compases detectados.",
    meter_confirmed: "Un segundo método (cada cuántos pulsos se repite la armonía) confirma el compás.",
    subdivision_binary: "Cada pulso se divide en 2 (subdivisión binaria).",
    subdivision_ternary: "Cada pulso se divide en 3 (subdivisión ternaria).",
    subdivision_unclear: "No queda claro si cada pulso se divide en 2 o en 3.",

    // Key card
    key_title: "Tonalidad",
    key_name: "{tonic} {mode}",
    major: "mayor",
    minor: "menor",
    key_alternatives: "También podría ser: {keys}.",
    key_reason_relative: "su relativa",
    key_reason_runner_up: "segunda opción del modelo",
    key_chords_same: "Los acordes detectados apuntan a la misma tonalidad.",
    key_chords_relative: "Los acordes detectados apuntan a {key}, su relativa.",
    key_chords_different: "Los acordes detectados apuntan a {key}: no coincide, así que hay dudas.",
    key_change: "Posible cambio de tonalidad: entre {start} y {end} parece estar en {key}.",

    // Chords and bars
    chords_note_simple:
      "Modo simple: solo mayor y menor, que es lo más confiable. Pasá a “Completos” para ver séptimas, bajos e inversiones.",
    chords_note_full: "Modo completo: incluye séptimas, bajos e inversiones, que fallan más seguido.",
    grid_note: "Hacé clic en un compás para escucharlo desde ahí.",
    grid_note_approximate:
      "Grilla aproximada: no se sabe con seguridad en qué pulso empieza cada compás. Hacé clic en un compás para escucharlo desde ahí.",
    no_chords: "No se detectaron acordes.",
    no_bars: "No se detectaron compases.",
    listen_from: "Escuchar desde {time}",
    bar: "compás {number}",
    section: "tramo {number}",
    pickup: "anacrusa",
    intro: "intro",

    // Messages from the analysis (codes in orfeo/messages.py)
    ffmpeg_missing: "No encontré ffmpeg. Instalalo con:  winget install Gyan.FFmpeg  y volvé a abrir la terminal.",
    no_audio_track: "El archivo no tiene ninguna pista de audio.",
    drm_protected: "El archivo está protegido con DRM y no se puede leer.",
    not_media: "No pude leer el archivo: no parece ser audio o video válido.",
    ffmpeg_failed: "ffmpeg no pudo leer el archivo: {detail}",
    too_short: "El audio dura menos de {seconds} segundos: es muy corto para analizarlo.",
    too_long:
      "El audio dura más de {minutes} minutos, que es el máximo (para mezclas largas, cortá la canción que te interesa).",
    silent: "El audio está en silencio.",
    all_tracks_silent: "Las {tracks} pistas de audio del archivo están en silencio.",
    too_large: "El archivo es demasiado grande (máximo {gigabytes} GB).",
    save_failed: "No pude guardar el archivo en el disco: {detail}",
    empty_file: "El archivo está vacío.",
    unexpected_error: "Error inesperado al analizar: {detail}",
    job_not_found: "No existe ese análisis (¿se reinició el servidor?).",
    queued: "En espera",
    loading_models: "Cargando los modelos (la primera vez tarda un poco)",
    extracting_audio: "Extrayendo el audio",
    finding_beats: "Buscando los pulsos y los primeros tiempos",
    tempo_and_meter: "Calculando el tempo y el compás",
    finding_key: "Buscando la tonalidad",
    recognizing_chords: "Reconociendo los acordes",
    locating_bars: "Ubicando los compases",
    building_report: "Armando el reporte",
    done: "Listo",
    too_few_beats: "Se detectaron muy pocos pulsos para estimar el tempo.",
    beats_corrected:
      "En algunos tramos el detector marcó pulsos de más (el doble) o de menos: se corrigieron {count} pulsos para que la grilla quede pareja y se puedan contar los compases.",
    too_few_downbeats: "No se detectaron suficientes primeros tiempos para estimar el compás.",
    all_beats_downbeats:
      "Casi todos los pulsos detectados quedaron marcados como primer tiempo, así que no se pudo contar el compás. Pasa con música muy libre o con mucho rubato.",
    meter_from_harmony:
      "El detector de primeros tiempos marcó compases de {counted} pulsos, pero la armonía y el bajo se repiten cada {beats} pulsos: lo más probable es que el compás sea de {beats}. Los detectores automáticos se entrenaron casi solo con música en 4/4 y tienden a forzarlo.",
    meter_from_harmony_only:
      "Los primeros tiempos detectados no alcanzaron para contar el compás, pero la armonía y el bajo se repiten cada {beats} pulsos.",
    harmony_suggests:
      "Un segundo método (cada cuántos pulsos se repite la armonía) sugiere compases de {beats} pulsos: escuchalo con el clic activado para decidir.",
    inconsistent_bars:
      "Los compases detectados no cuentan siempre lo mismo: puede que el compás cambie durante la canción o que los primeros tiempos estén mal ubicados.",
    ternary_ambiguity:
      "El 3/4 y el 6/8 se confunden con mucha facilidad (y en la chacarera o la zamba se alternan a propósito). Ninguna herramienta automática los distingue bien: escuchá si el pulso que marcás con el pie se divide en 2 o en 3.",
    approximate_grid:
      "No se pudo determinar con seguridad en qué pulso empieza cada compás: la grilla de compases es aproximada (puede estar corrida algunos pulsos).",
    or: "o {signature}",
    or_either: "o {first}, o {second}",
    or_counted_faster: "o {signature} contado más rápido",
    or_with_triplets: "o {signature} con tresillos",
    or_shuffle: "o shuffle; también se puede escribir en 12/8",
    or_odd_meter: "o {signature} (compás irregular)",
    unusual_meter: "compás poco común: tomalo con pinzas",
    tuning_sharp:
      "La grabación está {cents} cents más aguda que la afinación estándar (La = 440 Hz). Con un desvío así, la tonalidad y los acordes pueden salir corridos medio tono.",
    tuning_flat:
      "La grabación está {cents} cents más grave que la afinación estándar (La = 440 Hz). Con un desvío así, la tonalidad y los acordes pueden salir corridos medio tono.",
  },
};

let language = "es";

/** Text for `key` in the current language, with its {parameters} filled in. */
function t(key, params = {}) {
  const text = MESSAGES[language][key] ?? MESSAGES.es[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

/** Text of a message returned by the server ({code, params}); plain strings pass through. */
function messageText(message) {
  if (!message) return "";
  if (typeof message === "string") return message;
  return t(message.code, message.params);
}
