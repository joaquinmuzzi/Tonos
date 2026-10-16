"use strict";

/*
 * Texts of the interface, by language. The analysis does not return finished sentences but
 * message codes with parameters (see tonos/messages.py); their translations live here too.
 * "{name}" is replaced by the parameter with that name. To add a language, add a block with
 * every key of `en` and a button with its data-language in index.html.
 */
const MESSAGES = {
  en: {
    // Page
    stems_title: "tracks",
    separate_button: "Separate tracks",
    separate_hint: "Vocals, drums, bass and the rest, to mute or solo each one. It takes about a third of the song's length.",
    stems_off: "Back to the original mix",
    cancel: "cancel",
    stem_vocals: "vocals",
    stem_drums: "drums",
    stem_bass: "bass",
    stem_other: "other",
    stem_mute: "Mute",
    stem_solo: "Solo",
    rail_install: "install",
    demo_badge: "demo",
    demo_credit: "Song: “{title}” by {author}",
    demo_install: "Install Tonos to analyze your own songs",
    demo_failed: "Could not load the demo song.",
    rail_analyze: "analyze",
    rail_about: "about",
    state_on: "on",
    state_off: "off",
    speed_label: "Speed",
    slower: "Slower",
    faster: "Faster",
    notation_short: "notation",
    chords_short: "chords",
    star_on_github: "star on GitHub",
    click_short: "click",
    follow_short: "follow",
    simple_short: "simple",
    full_short: "full",
    could_be: "could also be",
    notes_title: "notes",
    hear_else: "hear something else?",
    report_result: "→ report a wrong result",
    contribute: "→ contribute on GitHub",
    beat_length: "1 beat = {seconds} s",
    swing: "swing",
    sub_binary: "in eighths",
    sub_ternary: "in triplets",
    sub_unclear: "subdivision unclear",
    alt_double: "{bpm} bpm (double)",
    alt_half: "{bpm} bpm (half)",
    uncertain_tempo: "The tempo is uncertain: check it with the click.",
    uncertain_meter: "The meter is uncertain: check it with the click.",
    uncertain_key: "The key is uncertain.",
    bars_count: "{count} bars",
    tagline:
      "Upload a song or a video and get its tempo, meter, key and chords. Everything runs on your computer: the file never leaves it.",
    language_label: "Language",
    dropzone_title: "Drag a file here or click to choose one",
    dropzone_hint: "MP4, MP3, M4A, WAV, FLAC, MKV… up to 20 minutes (and 1 GB)",
    progress_label: "Analysis progress",
    retry: "Try another file",
    audio_unsupported: "Your browser cannot play this format, but the analysis is complete.",
    click_toggle: "Click on every beat",
    notation_label: "Notation",
    detail_label: "Chord detail",
    reliability_title: "How reliable is this?",
    reliability_tempo_title: "Tempo and beats:",
    reliability_tempo:
      "very good for pop, rock and electronic music with drums. The typical error is giving double or half the tempo. Much worse for music without drums, live recordings or rubato. Turn on the click to check it by ear.",
    reliability_meter_title: "Meter:",
    reliability_meter:
      "the hardest part. It counts the beats between downbeats, and downbeats fail more often than beats (about 1 in 5). 3/4 and 6/8 cannot be told apart automatically.",
    reliability_key_title: "Key:",
    reliability_key:
      "in published tests, the model gets the exact key right for 7 to 8 songs out of 10. When it fails, it almost always confuses it with the relative key (C major ↔ A minor) or with a fifth. It gives a single key per song, and modal music (Dorian, Mixolydian…) is forced into major or minor.",
    reliability_chords_title: "Chords:",
    reliability_chords:
      "correct about 78 % of the time for major/minor, less with sevenths and unusual chords. That is why they start in “simple” mode. Basses and inversions often fail.",
    reliability_repertoire_title: "Repertoire:",
    reliability_repertoire:
      "the models were trained mostly on pop and rock sung in English. Folk, tango and other Latin American genres may give worse results.",
    models_credit:
      "Models: Beat This! (CPJKU, 2024), S-KEY (Deezer, 2025) and Consonance-ACE (Poltronieri, Serra and Rocamora, 2025), plus librosa for the control tempo and the tuning.",
    another_song: "Analyze another song",
    download_json: "Download data (JSON)",

    // Confidence badges

    // Upload and progress
    too_large_client:
      "The file is too large (maximum 1 GB). If it is a video, try a lighter version or just the audio.",
    uploading: "Uploading the file…",
    uploading_percent: "Uploading the file… {percent}",
    server_error: "The server answered with an error ({status}).",
    connection_failed: "Could not connect to Tonos. Is its window still open?",
    connection_lost: "Lost the connection to Tonos: {detail}",

    // Tempo card
    tempo_title: "Tempo",

    // Meter card
    meter_title: "Meter",
    meter_beats_per_bar: "{beats} beats per bar",

    // Key card
    key_title: "Key",
    key_name: "{tonic} {mode}",
    major: "major",
    minor: "minor",
    key_reason_relative: "its relative key",
    key_reason_runner_up: "the model's second choice",
    key_change: "Possible key change: between {start} and {end} it seems to be in {key}.",

    // Chords and bars
    no_bars: "No bars were detected.",
    listen_from: "Listen from {time}",
    grid_note: "Click a bar to listen from there.",
    grid_note_approximate: "Approximate grid: it is not certain on which beat each bar starts. Click a bar to listen from there.",
    bar: "bar {number}",
    section: "section {number}",
    pickup: "pickup",
    intro: "intro",

    // Messages from the analysis (codes in tonos/messages.py)
    ffmpeg_missing:
      "ffmpeg was not found. Install it (on Windows: winget install Gyan.FFmpeg) and open the terminal again.",
    no_audio_track: "The file has no audio track.",
    drm_protected: "The file is DRM-protected and cannot be read.",
    not_media: "Could not read the file: it does not look like valid audio or video.",
    ffmpeg_failed: "ffmpeg could not read the file: {detail}",
    too_short: "The audio is shorter than {seconds} seconds: too short to analyze.",
    too_long:
      "The audio is longer than {minutes} minutes, which is the maximum (for long mixes, cut out the song you are interested in).",
    silent: "The audio is silent.",
    all_tracks_silent: "All {tracks} audio tracks of the file are silent.",
    too_large: "The file is too large (maximum {gigabytes} GB).",
    save_failed: "Could not save the file to disk: {detail}",
    empty_file: "The file is empty.",
    unexpected_error: "Unexpected error during the analysis: {detail}",
    job_not_found: "That analysis does not exist (was the server restarted?).",
    queued: "Waiting",
    loading_models: "Loading the models (the first time takes a while)",
    extracting_audio: "Extracting the audio",
    finding_beats: "Finding the beats and downbeats",
    tempo_and_meter: "Computing the tempo and the meter",
    finding_key: "Finding the key",
    recognizing_chords: "Recognizing the chords",
    locating_bars: "Locating the bars",
    building_report: "Building the report",
    separating_tracks: "Separating the tracks",
    separation_cancelled: "The separation was cancelled.",
    done: "Done",
    too_few_beats: "Too few beats were detected to estimate the tempo.",
    beats_corrected:
      "In some stretches the detector marked extra beats (double time) or missed some: {count} beats were corrected so that the grid is even and the bars can be counted.",
    beats_retracked:
      "The beat detector could not follow a steady beat (a single instrument, pauses or a free tempo), so the beat was estimated again at a steady tempo: the one at which the harmony repeats most clearly. Check it with the click.",
    too_few_downbeats: "Not enough downbeats were detected to estimate the meter.",
    all_beats_downbeats:
      "Almost every detected beat was marked as a downbeat, so the meter could not be counted. This happens with very free music or a lot of rubato.",
    meter_from_harmony:
      "The downbeat detector marked bars of {counted} beats, but the harmony and the bass repeat every {beats} beats: the meter is most likely in {beats}. Automatic detectors were trained almost only on 4/4 music and tend to force it.",
    meter_from_harmony_only:
      "The detected downbeats were not enough to count the meter, but the harmony and the bass repeat every {beats} beats.",
    harmony_suggests:
      "A second method (how often the harmony repeats) suggests bars of {beats} beats: listen with the click on to decide.",
    inconsistent_bars:
      "The detected bars do not always have the same number of beats: the meter may change during the song, or the downbeats may be misplaced.",
    ternary_ambiguity:
      "3/4 and 6/8 are very easy to confuse (and some styles, like the chacarera or the zamba, alternate them on purpose). No automatic tool tells them apart well: listen to whether the beat you tap with your foot divides into 2 or into 3.",
    approximate_grid:
      "Could not determine reliably on which beat each bar starts: the bar grid is approximate (it may be shifted by a few beats).",
    or: "or {signature}",
    or_either: "or {first}, or {second}",
    or_counted_faster: "or {signature} counted faster",
    or_with_triplets: "or {signature} with triplets",
    or_shuffle: "or shuffle; it can also be written in 12/8",
    or_odd_meter: "or {signature} (odd meter)",
    unusual_meter: "an unusual meter: take it with a grain of salt",
    tuning_sharp:
      "The recording is {cents} cents sharp of standard tuning (A = 440 Hz). With such a deviation, the key and the chords may come out a semitone off.",
    tuning_flat:
      "The recording is {cents} cents flat of standard tuning (A = 440 Hz). With such a deviation, the key and the chords may come out a semitone off.",
  },
  es: {
    // Page
    stems_title: "pistas",
    separate_button: "Separar pistas",
    separate_hint: "Voz, batería, bajo y el resto, para silenciar o escuchar cada una sola. Tarda alrededor de un tercio de lo que dura el tema.",
    stems_off: "Volver a la mezcla original",
    cancel: "cancelar",
    stem_vocals: "voz",
    stem_drums: "batería",
    stem_bass: "bajo",
    stem_other: "resto",
    stem_mute: "Silenciar",
    stem_solo: "Escuchar sola",
    rail_install: "instalar",
    demo_badge: "demo",
    demo_credit: "Canción: “{title}” de {author}",
    demo_install: "Instalá Tonos para analizar tus canciones",
    demo_failed: "No se pudo cargar la canción de la demo.",
    rail_analyze: "analizar",
    rail_about: "info",
    state_on: "on",
    state_off: "off",
    speed_label: "Velocidad",
    slower: "Más lento",
    faster: "Más rápido",
    notation_short: "notación",
    chords_short: "acordes",
    star_on_github: "star en GitHub",
    click_short: "clic",
    follow_short: "seguir",
    simple_short: "simples",
    full_short: "completos",
    could_be: "también podría ser",
    notes_title: "notas",
    hear_else: "¿escuchás otra cosa?",
    report_result: "→ reportar un resultado",
    contribute: "→ contribuir en GitHub",
    beat_length: "1 pulso = {seconds} s",
    swing: "con swing",
    sub_binary: "en corcheas",
    sub_ternary: "en tresillos",
    sub_unclear: "subdivisión dudosa",
    alt_double: "{bpm} bpm (al doble)",
    alt_half: "{bpm} bpm (a la mitad)",
    uncertain_tempo: "El tempo es incierto: comprobalo con el clic.",
    uncertain_meter: "El compás es incierto: comprobalo con el clic.",
    uncertain_key: "La tonalidad es incierta.",
    bars_count: "{count} compases",
    tagline:
      "Subí una canción o un video y te digo el tempo, el compás, la tonalidad y los acordes. Todo se procesa en tu PC: el archivo no sale de tu computadora.",
    language_label: "Idioma",
    dropzone_title: "Arrastrá un archivo acá o hacé clic para elegirlo",
    dropzone_hint: "MP4, MP3, M4A, WAV, FLAC, MKV… de hasta 20 minutos (y 1 GB)",
    progress_label: "Progreso del análisis",
    retry: "Probar con otro archivo",
    audio_unsupported: "Tu navegador no puede reproducir este formato, pero el análisis está completo.",
    click_toggle: "Clic en cada pulso",
    notation_label: "Notación",
    detail_label: "Detalle de los acordes",
    reliability_title: "¿Qué tan confiable es esto?",
    reliability_tempo_title: "Tempo y pulsos:",
    reliability_tempo:
      "muy buenos en pop, rock y electrónica con batería. El error típico es dar el doble o la mitad. En música sin batería, en vivo o con rubato, bastante peor. Activá el clic para comprobarlo de oído.",
    reliability_meter_title: "Compás:",
    reliability_meter:
      "es lo más difícil. Se cuenta cuántos pulsos hay entre primeros tiempos, y los primeros tiempos fallan más que los pulsos (más o menos 1 de cada 5). El 3/4 y el 6/8 no se pueden distinguir de forma automática.",
    reliability_key_title: "Tonalidad:",
    reliability_key:
      "en pruebas publicadas, el modelo acierta exacto entre 7 y 8 de cada 10 canciones. Cuando falla, casi siempre se confunde con la relativa (Do mayor ↔ La menor) o con una quinta. Da una sola tonalidad por canción, y la música modal (dórica, mixolidia…) se fuerza a mayor o menor.",
    reliability_chords_title: "Acordes:",
    reliability_chords:
      "alrededor de 78 % del tiempo correcto en mayor/menor, menos con séptimas y acordes raros. Por eso arrancan en modo “simple”. Los bajos e inversiones fallan seguido.",
    reliability_repertoire_title: "Repertorio:",
    reliability_repertoire:
      "los modelos se entrenaron sobre todo con pop y rock en inglés. Folklore, tango y otros géneros latinos pueden dar peores resultados.",
    models_credit:
      "Modelos: Beat This! (CPJKU, 2024), S-KEY (Deezer, 2025) y Consonance-ACE (Poltronieri, Serra y Rocamora, 2025), más librosa para el tempo de control y la afinación.",
    another_song: "Analizar otra canción",
    download_json: "Descargar datos (JSON)",

    // Confidence badges

    // Upload and progress
    too_large_client:
      "El archivo es demasiado grande (máximo 1 GB). Si es un video, probá con una versión más liviana o solo con el audio.",
    uploading: "Subiendo el archivo…",
    uploading_percent: "Subiendo el archivo… {percent}",
    server_error: "El servidor respondió con un error ({status}).",
    connection_failed: "No me pude conectar con Tonos. ¿Sigue abierta su ventana?",
    connection_lost: "Perdí la conexión con Tonos: {detail}",

    // Tempo card
    tempo_title: "Tempo",

    // Meter card
    meter_title: "Compás",
    meter_beats_per_bar: "{beats} pulsos por compás",

    // Key card
    key_title: "Tonalidad",
    key_name: "{tonic} {mode}",
    major: "mayor",
    minor: "menor",
    key_reason_relative: "su relativa",
    key_reason_runner_up: "segunda opción del modelo",
    key_change: "Posible cambio de tonalidad: entre {start} y {end} parece estar en {key}.",

    // Chords and bars
    no_bars: "No se detectaron compases.",
    listen_from: "Escuchar desde {time}",
    grid_note: "Hacé clic en un compás para escucharlo desde ahí.",
    grid_note_approximate: "Grilla aproximada: no se sabe con seguridad en qué pulso empieza cada compás. Hacé clic en un compás para escucharlo desde ahí.",
    bar: "compás {number}",
    section: "tramo {number}",
    pickup: "anacrusa",
    intro: "intro",

    // Messages from the analysis (codes in tonos/messages.py)
    ffmpeg_missing:
      "No encontré ffmpeg. Instalalo con:  winget install Gyan.FFmpeg  y volvé a abrir la terminal.",
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
    separating_tracks: "Separando las pistas",
    separation_cancelled: "Se canceló la separación.",
    done: "Listo",
    too_few_beats: "Se detectaron muy pocos pulsos para estimar el tempo.",
    beats_corrected:
      "En algunos tramos el detector marcó pulsos de más (el doble) o de menos: se corrigieron {count} pulsos para que la grilla quede pareja y se puedan contar los compases.",
    beats_retracked:
      "El detector no pudo seguir un pulso estable (un solo instrumento, pausas o tempo libre), así que el pulso se volvió a estimar con un tempo constante: el que hace más clara la repetición de la armonía. Comprobalo con el clic.",
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

const LANGUAGES = Object.keys(MESSAGES);

/** The saved choice, or the first language of the browser that we have, or English. */
function detectLanguage() {
  try {
    const saved = localStorage.getItem("tonos-language");
    if (LANGUAGES.includes(saved)) return saved;
  } catch {
    /* no storage */
  }
  for (const tag of navigator.languages || [navigator.language || ""]) {
    const base = tag.toLowerCase().split("-")[0];
    if (LANGUAGES.includes(base)) return base;
  }
  return "en";
}

let language = detectLanguage();

/** Text for `key` in the current language, with its {parameters} filled in. */
function t(key, params = {}) {
  const text = MESSAGES[language][key] ?? MESSAGES.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

/** Text of a message ({code, params}, from the server or the page); plain strings pass through. */
function messageText(message) {
  if (!message) return "";
  if (typeof message === "string") return message;
  return t(message.code, message.params);
}

/** Translates the fixed texts of the page (data-i18n, data-i18n-aria-label, data-i18n-title). */
function translatePage() {
  document.documentElement.lang = language;
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-aria-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  }
  for (const node of document.querySelectorAll("[data-i18n-title]")) {
    node.setAttribute("title", t(node.dataset.i18nTitle));
  }
}
