"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  result: null,
  url: null, // local URL of the chosen file, to play it without uploading it again
  title: null, // shown instead of the file name (in the online demo)
  notation: readPreference("notation", language === "es" ? "solfege" : "letter"),
  detail: readPreference("detail", "simple"),
  beats: [],
  beatNumbers: [], // number of each beat within its bar (1 = downbeat)
  beatColors: [], // colour of the chord that sounds on each beat
  downbeats: new Set(),
  activeBar: -1,
  nextClick: 0,
  timer: null,
  error: null, // message shown in the error box, kept to translate it again
  click: false,
  follow: true,
  file: null, // the chosen file, sent again to separate its tracks
  volume: Math.min(1, Math.max(0, Number(readPreference("volume", "1")) || 0)), // 0..1, remembered
  volumeOff: false, // the speaker button: silent without forgetting the volume
  pitch: 0, // semitones the song is moved up or down (the names and the sound)
};

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5];
const MAX_PITCH = 6; // semitones up or down
const DEMO = window.TONOS_DEMO; // set only in the online demo (static/demo.js)
const audio = $("audio");
let audioContext = null;

// ---------------------------------------------------------------- helpers

function readPreference(key, fallback) {
  try {
    return localStorage.getItem("tonos-" + key) || fallback;
  } catch {
    return fallback;
  }
}

function savePreference(key, value) {
  try {
    localStorage.setItem("tonos-" + key, value);
  } catch {
    /* no storage: nothing to do */
  }
}

/** Creates an element. Texts go in as textContent (never as HTML). */
function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

/** A message of the page itself, shaped like the ones the server sends. */
const local = (code, params = {}) => ({ code, params });

/** The message in an error response of the server, or a generic one. */
const serverMessage = (detail, status) => (detail && detail.code ? detail : local("server_error", { status }));

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const percent = (x) => `${Math.round(x * 100)} %`;
const rounded = (x) => String(Math.round(x));

/** Last index i such that list[i][key] <= time (or -1). */
function search(list, time, key = "start") {
  let low = 0;
  let high = list.length - 1;
  let answer = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    const value = key ? list[middle][key] : list[middle];
    if (value <= time) {
      answer = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return answer;
}

function show(section) {
  for (const id of ["upload", "progress", "error", "report"]) $(id).hidden = id !== section;
  updateSeparateButton();
}

/**
 * Colour of a chord: the hue follows the circle of fifths from its root, so chords a fifth apart
 * get neighbouring colours (C, G, D...). Minor chords are darker; no chord is gray.
 */
function chordColor(segment) {
  if (!segment || !segment.is_chord || segment.root_pc === null) return "#3a352f";
  segment = movedChord(segment);
  const hue = ((segment.root_pc * 7) % 12) * 30;
  const minor = /m(?!aj)/.test(segment.letter_simple || "");
  // Muted colours, so the timeline and the grid do not shout on the warm background
  return `hsl(${hue}, ${minor ? 32 : 42}%, ${minor ? 46 : 58}%)`;
}

// ---------------------------------------------------------------- upload

const dropzone = $("dropzone");
const fileInput = $("file-input");

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) upload(fileInput.files[0]);
  fileInput.value = "";
});
dropzone.addEventListener("dragover", () => dropzone.classList.add("dragover"));
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
// Files dropped anywhere on the page are accepted (also on a report, to analyze another
// song). Without this, the browser would open the file and everything would be lost.
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (DEMO || !$("progress").hidden) return; // the demo does not analyze; or one is running
  if (e.dataTransfer && e.dataTransfer.files.length) upload(e.dataTransfer.files[0]);
});

const MAX_UPLOAD_BYTES = 1024 ** 3;

function setProgress(text, fraction) {
  $("step").textContent = text;
  const value = Math.max(0, Math.min(100, fraction * 100));
  $("progress-fill").style.width = `${value}%`;
  $("progress-track").setAttribute("aria-valuenow", String(Math.round(value)));
}

function upload(file) {
  if (file.size > MAX_UPLOAD_BYTES) {
    showError(local("too_large_client"));
    return;
  }
  stopPlayback();
  state.result = null;
  state.error = null;
  if (state.url) URL.revokeObjectURL(state.url);
  state.url = URL.createObjectURL(file);
  state.file = file;
  resetStems();
  setSong(file.name.replace(/\.[^.]+$/, ""), "");

  show("progress");
  setProgress(t("uploading"), 0);
  const start = performance.now();
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    $("elapsed").textContent = `${Math.round((performance.now() - start) / 1000)} s`;
  }, 500);

  const form = new FormData();
  form.append("file", file);
  const request = new XMLHttpRequest();
  request.open("POST", "/api/analyses");
  request.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      setProgress(t("uploading_percent", { percent: percent(e.loaded / e.total) }), 0.02 * (e.loaded / e.total));
    }
  });
  request.addEventListener("load", () => {
    let body = {};
    try {
      body = JSON.parse(request.responseText);
    } catch {
      /* empty response */
    }
    if (request.status === 200 && body.id) poll(body.id);
    else showError(serverMessage(body.detail, request.status));
  });
  request.addEventListener("error", () => showError(local("connection_failed")));
  request.send(form);
}

async function poll(id) {
  let failures = 0;
  for (;;) {
    let job;
    try {
      const response = await fetch(`/api/analyses/${id}`);
      job = await response.json();
      if (!response.ok) throw new Error(messageText(serverMessage(job.detail, response.status)));
      failures = 0;
    } catch (error) {
      if (++failures >= 5) {
        showError(local("connection_lost", { detail: error.message }));
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    if (job.status === "done") {
      clearInterval(state.timer);
      showReport(job.result);
      return;
    }
    if (job.status === "error") {
      showError(job.error);
      return;
    }
    setProgress(`${t(job.step)}…`, job.progress);
    await new Promise((r) => setTimeout(r, 600));
  }
}

function showError(message) {
  clearInterval(state.timer);
  state.error = message;
  $("error-text").textContent = messageText(message);
  show("error");
}

$("retry").addEventListener("click", () => (DEMO ? location.reload() : show("upload")));
$("new-analysis").addEventListener("click", () => {
  stopPlayback();
  state.result = null;
  resetStems();
  setSong("Tonos", null);
  show("upload");
  window.scrollTo({ top: 0 });
});

$("download").addEventListener("click", () => {
  if (!state.result) return;
  const blob = new Blob([JSON.stringify(state.result, null, 2)], { type: "application/json" });
  const link = el("a", { href: URL.createObjectURL(blob), download: `${state.result.file.name}.tonos.json` });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});

// ---------------------------------------------------------------- report

/** Title and second line of the top bar; meta === null shows the tagline. */
function setSong(title, meta) {
  $("song-title").textContent = title;
  const line = $("song-meta");
  if (meta === null) {
    line.dataset.i18n = "tagline";
    line.textContent = t("tagline");
  } else {
    delete line.dataset.i18n;
    line.textContent = meta;
  }
}

function showReport(result) {
  state.result = result;
  state.pitch = 0;
  movedChords = new WeakMap();
  markButtons();
  applyPitch();
  state.beats = result.beats;
  state.downbeats = new Set(result.downbeats.map((time) => time.toFixed(3)));
  state.beatNumbers = numberBeats(result);
  state.activeBar = -1;

  $("audio-error").hidden = true;
  if (!stemsPlaying() && !stems.job && !stems.request) showStems("start");
  if (state.url) audio.src = state.url;
  $("play").disabled = false;
  $("version").textContent = `MIT · v${result.tonos_version}`;

  markButtons();
  drawReport();
  show("report");
  updatePlayback();
}

/** Number of each beat within its bar (1 = downbeat). */
function numberBeats(result) {
  const perBar = result.meter.beats_per_bar;
  const first = result.downbeats.length ? result.downbeats[0] : Infinity;
  const pickup = result.beats.filter((time) => time < first).length;
  let counter = 0;
  return result.beats.map((time, i) => {
    if (state.downbeats.has(time.toFixed(3))) counter = 1;
    else if (counter > 0) counter += 1;
    // Before the first downbeat (a pickup): these are the last beats of a bar
    else return perBar && pickup < perBar ? perBar - pickup + i + 1 : null;
    return counter;
  });
}

/** Draws everything that depends on the language or the notation. */
function drawReport() {
  const result = state.result;
  const segments = result.chords.segments;
  state.beatColors = result.beats.map((time) => chordColor(segments[search(segments, time + 0.05)]));
  drawTempo(result.tempo);
  drawMeter(result.meter);
  drawKey(result.key);
  drawPanel(result);
  drawBars();
  state.activeBar = -1;
  updatePlayback();
}

function stat(id, label, value, ...details) {
  $(id).replaceChildren(el("div", { class: "label mono" }, label), value, ...details.filter(Boolean));
}

function drawTempo(tempo) {
  if (!tempo.bpm) {
    stat("tempo-stat", t("tempo_title"), el("div", { class: "value" }, "—"), el("div", { class: "detail" }, messageText(tempo.reason)));
    return;
  }
  const detail = `${t("beat_length", { seconds: (60 / tempo.bpm).toFixed(2) })} · ×2 ${rounded(tempo.alternatives.double)} · ÷2 ${rounded(tempo.alternatives.half)}`;
  stat(
    "tempo-stat",
    t("tempo_title"),
    el("div", { class: "value" }, rounded(tempo.bpm), el("small", {}, " bpm")),
    el("div", { class: "detail" }, detail)
  );
}

function drawMeter(meter) {
  if (!meter.beats_per_bar) {
    stat("meter-stat", t("meter_title"), el("div", { class: "value" }, "—"), el("div", { class: "detail" }, messageText(meter.reason)));
    return;
  }
  const reading = meter.time_signature || t("meter_beats_per_bar", { beats: meter.beats_per_bar });
  const kind = meter.swing ? "swing" : `sub_${meter.subdivision.kind}`;
  const squares = el("div", { class: "squares mono", id: "squares" });
  for (let i = 1; i <= Math.min(meter.beats_per_bar, 12); i++) squares.append(el("span", { "data-beat": String(i) }));
  squares.append(el("em", { class: "detail" }, t(kind)));
  stat("meter-stat", t("meter_title"), el("div", { class: "value" }, reading), squares);
}

/** A key as it sounds with the song moved by state.pitch semitones. */
function movedKey(key) {
  return TonosTranspose.key(key, state.pitch);
}

/** "Do", "C"... in the chosen notation. */
function tonicName(key, notation = state.notation) {
  return movedKey(key)[notation];
}

function keyName(key, notation = state.notation) {
  return t("key_name", { tonic: tonicName(key, notation), mode: t(key.mode) });
}

function drawKey(key) {
  const best = movedKey(key.best);
  const scale = best.scale ? best.scale[state.notation].join(" ") : "";
  stat(
    "key-stat",
    t("key_title"),
    el(
      "div",
      { class: "value" },
      tonicName(key.best),
      el("small", {}, ` ${t(best.mode)}`),
      state.pitch ? el("small", { class: "original-key" }, ` ${t("original_key", { tonic: key.best[state.notation] })}`) : null
    ),
    scale ? el("div", { class: "detail" }, scale) : null
  );
}

/** Other readings, and notes only where the analysis has doubts. */
function drawPanel(result) {
  const { tempo, meter, key, tuning } = result;
  const alternatives = key.alternatives.map((a) => `${keyName(a)} (${t(`key_reason_${a.reason}`)})`);
  if (tempo.bpm) {
    alternatives.push(t("alt_double", { bpm: rounded(tempo.alternatives.double) }));
    alternatives.push(t("alt_half", { bpm: rounded(tempo.alternatives.half) }));
  }
  if (meter.alternative) alternatives.push(messageText(meter.alternative));
  $("alternatives").replaceChildren(...alternatives.map((text) => el("li", {}, text)));

  const notes = [];
  if (tempo.bpm && tempo.confidence === "low") notes.push(t("uncertain_tempo"));
  if (meter.beats_per_bar && meter.confidence === "low") notes.push(t("uncertain_meter"));
  if (key.confidence === "low") notes.push(t("uncertain_key"));
  if (tempo.warning) notes.push(messageText(tempo.warning));
  for (const warning of meter.warnings || []) notes.push(messageText(warning));
  for (const change of key.sections.changes) {
    notes.push(t("key_change", { start: mmss(change.start), end: mmss(change.end), key: keyName(change) }));
  }
  if (tuning.warning) notes.push(messageText(tuning.warning));
  $("notes").replaceChildren(...notes.map((text) => el("p", {}, text)));
  $("notes-section").hidden = notes.length === 0;
}

/** A chord segment as it sounds with the song moved; kept until the pitch changes. */
let movedChords = new WeakMap();
function movedChord(segment) {
  if (!state.pitch || !segment || !segment.is_chord) return segment;
  if (!movedChords.has(segment)) {
    const best = state.result.key.best;
    const speller = new TonosTranspose.Speller(best.tonic_pc + state.pitch, best.mode);
    movedChords.set(segment, TonosTranspose.chord(segment, state.pitch, speller));
  }
  return movedChords.get(segment);
}

function chordName(segment) {
  if (!segment) return "—";
  return movedChord(segment)[state.detail === "simple" ? `${state.notation}_simple` : state.notation];
}

function barLabel(bar) {
  return t(bar.kind, { number: bar.number });
}

function chordsOfBar(bar) {
  const names = [];
  for (const i of bar.chords) {
    const name = chordName(state.result.chords.segments[i]);
    if (names[names.length - 1] !== name) names.push(name);
  }
  return names.length ? names.join(" · ") : "—";
}

function drawBars() {
  const result = state.result;
  $("bars-title").textContent = t("bars_count", { count: result.bars.length });
  $("grid-note").textContent = t(result.meter.approximate_grid ? "grid_note_approximate" : "grid_note");
  const cells = result.bars.map((bar, i) => {
    const first = result.chords.segments[bar.chords[0]];
    return el(
      "button",
      {
        type: "button",
        class: "bar-cell",
        "data-i": String(i),
        title: t("listen_from", { time: mmss(bar.start) }),
        style: `border-top-color: ${chordColor(first)}`,
        onclick: () => {
          audio.currentTime = bar.start;
          play();
        },
      },
      el("span", { class: "num" }, bar.kind === "bar" ? String(bar.number) : barLabel(bar)),
      el("span", { class: "chord-names" }, chordsOfBar(bar))
    );
  });
  $("bar-grid").replaceChildren(...cells);
  if (!cells.length) $("bar-grid").append(el("p", { class: "note" }, t("no_bars")));
}

// ---------------------------------------------------------------- timeline (canvas)

const strip = $("strip");

function drawStrip(now) {
  const beats = state.beats;
  const duration = state.result ? state.result.file.duration : 0;
  const ratio = window.devicePixelRatio || 1;
  const width = strip.clientWidth;
  const height = strip.clientHeight;
  if (strip.width !== Math.round(width * ratio)) {
    strip.width = Math.round(width * ratio);
    strip.height = Math.round(height * ratio);
  }
  const g = strip.getContext("2d");
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  g.clearRect(0, 0, width, height);
  if (!duration || !beats.length) return;
  const x = (time) => (time / duration) * width;
  const current = search(beats, now, null);
  // A beat lasts until the next one, but not across a pause without beats
  const typical = beats.length > 1 ? (beats[beats.length - 1] - beats[0]) / (beats.length - 1) : 0.5;
  for (let i = 0; i < beats.length; i++) {
    const left = x(beats[i]);
    const end = i + 1 < beats.length ? Math.min(beats[i + 1], beats[i] + 2 * typical) : beats[i] + typical;
    const right = x(Math.min(duration, end));
    g.globalAlpha = beats[i] <= now ? 1 : 0.35;
    g.fillStyle = state.beatColors[i];
    g.fillRect(left, 0, Math.max(1, right - left - 1), height);
    if (state.downbeats.has(beats[i].toFixed(3))) {
      g.globalAlpha = 1;
      g.fillStyle = "#22201d";
      g.fillRect(left - 1, 0, 2, height);
    }
  }
  g.globalAlpha = 1;
  if (current >= 0) {
    const left = x(beats[current]);
    const right = current + 1 < beats.length ? x(beats[current + 1]) : left + 3;
    g.strokeStyle = "#e2ddd4";
    g.lineWidth = 2;
    g.strokeRect(left + 1, 1, Math.max(2, right - left - 2), height - 2);
  }
}

strip.addEventListener("click", (e) => {
  if (!state.result) return;
  const rect = strip.getBoundingClientRect();
  audio.currentTime = ((e.clientX - rect.left) / rect.width) * state.result.file.duration;
  updatePlayback();
});
window.addEventListener("resize", () => drawStrip(audio.currentTime));
// Hovering the timeline names the chord and the bar at that point
strip.addEventListener("mousemove", (e) => {
  if (!state.result) return;
  const rect = strip.getBoundingClientRect();
  const time = ((e.clientX - rect.left) / rect.width) * state.result.file.duration;
  const segments = state.result.chords.segments;
  const bars = state.result.bars;
  const bar = bars[search(bars, time)];
  strip.title = `${mmss(time)} · ${chordName(segments[search(segments, time)])}${bar ? ` · ${barLabel(bar)}` : ""}`;
});

// ---------------------------------------------------------------- controls

function markButtons() {
  for (const button of document.querySelectorAll("[data-language]")) {
    button.setAttribute("aria-pressed", String(button.dataset.language === language));
  }
  for (const button of document.querySelectorAll("[data-notation]")) {
    button.setAttribute("aria-pressed", String(button.dataset.notation === state.notation));
  }
  for (const button of document.querySelectorAll("[data-detail]")) {
    button.setAttribute("aria-pressed", String(button.dataset.detail === state.detail));
  }
  $("click").setAttribute("aria-pressed", String(state.click));
  $("click-state").textContent = t(state.click ? "state_on" : "state_off");
  $("follow").setAttribute("aria-pressed", String(state.follow));
  $("speed").textContent = `${audio.playbackRate}×`;
  $("pitch").textContent = state.pitch > 0 ? `+${state.pitch}` : state.pitch < 0 ? `−${-state.pitch}` : "0";
  $("pitch").classList.toggle("changed", state.pitch !== 0);
  $("pitch-down").disabled = state.pitch <= -MAX_PITCH;
  $("pitch-up").disabled = state.pitch >= MAX_PITCH;
}

function setLanguage(code) {
  language = code;
  savePreference("language", code);
  translatePage();
  markButtons();
  if (state.error) $("error-text").textContent = messageText(state.error);
  if (state.result) drawReport();
  if (DEMO) drawDemoBar();
  if (stemsPlaying()) drawMixer();
  if (stems.error) $("stems-error").textContent = messageText(stems.error);
}

for (const button of document.querySelectorAll("[data-language]")) {
  button.addEventListener("click", () => setLanguage(button.dataset.language));
}
for (const button of document.querySelectorAll("[data-notation]")) {
  button.addEventListener("click", () => {
    state.notation = button.dataset.notation;
    savePreference("notation", state.notation);
    markButtons();
    if (state.result) drawReport();
  });
}
for (const button of document.querySelectorAll("[data-detail]")) {
  button.addEventListener("click", () => {
    state.detail = button.dataset.detail;
    savePreference("detail", state.detail);
    markButtons();
    if (state.result) drawReport();
  });
}
$("click").addEventListener("click", () => {
  state.click = !state.click;
  markButtons();
  if (state.click) ensureAudioContext();
  resetClicks();
});
$("follow").addEventListener("click", () => {
  state.follow = !state.follow;
  markButtons();
});
function changeSpeed(step) {
  const index = Math.max(0, SPEEDS.indexOf(audio.playbackRate));
  audio.playbackRate = SPEEDS[Math.min(SPEEDS.length - 1, Math.max(0, index + step))];
  markButtons();
}
$("slower").addEventListener("click", () => changeSpeed(-1));
$("faster").addEventListener("click", () => changeSpeed(1));

function setPitch(semitones) {
  state.pitch = Math.max(-MAX_PITCH, Math.min(MAX_PITCH, semitones));
  movedChords = new WeakMap();
  markButtons();
  if (state.result) drawReport();
  applyPitch();
}
$("pitch-down").addEventListener("click", () => setPitch(state.pitch - 1));
$("pitch-up").addEventListener("click", () => setPitch(state.pitch + 1));

function play() {
  if (state.click || shifter.node) ensureAudioContext();
  audio.play().catch(() => {});
  for (const player of Object.values(stems.players)) {
    player.currentTime = audio.currentTime;
    player.play().catch(() => {});
  }
}

$("play").addEventListener("click", () => (audio.paused ? play() : audio.pause()));
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || !state.result || e.target.closest("input, textarea, select")) return;
  e.preventDefault();
  if (audio.paused) play();
  else audio.pause();
});

function setPlayIcon(playing) {
  $("play-icon").innerHTML = playing ? '<path d="M7 4h4v16H7zM13 4h4v16h-4z"/>' : '<path d="M7 4v16l13-8z"/>';
  $("play").setAttribute("aria-label", playing ? "Pause" : "Play");
}

// ---------------------------------------------------------------- playback

function updatePlayback() {
  if (!state.result) return;
  const now = audio.currentTime;
  const segments = state.result.chords.segments;
  const duration = state.result.file.duration;

  const i = search(segments, now);
  const current = i >= 0 && now < segments[i].end ? segments[i] : null;
  let next = null;
  for (let j = i + 1; j < segments.length; j++) {
    if (segments[j].is_chord && chordName(segments[j]) !== chordName(current)) {
      next = segments[j];
      break;
    }
  }
  setSong(
    state.title || state.result.file.name.replace(/\.[^.]+$/, ""),
    `${mmss(now)} / ${mmss(duration)} · ${chordName(current)} → ${chordName(next)}`
  );

  const bars = state.result.bars;
  const k = search(bars, now);
  if (k !== state.activeBar) {
    $("bar-grid").querySelector(".bar-cell.active")?.classList.remove("active");
    const cell = $("bar-grid").querySelector(`.bar-cell[data-i="${k}"]`);
    if (cell) {
      cell.classList.add("active");
      if (state.follow && !audio.paused) scrollGrid(cell);
    }
    state.activeBar = k;
  }

  const p = search(state.beats, now, null);
  const near = p >= 0 && now - state.beats[p] < 0.25;
  const perBar = state.result.meter.beats_per_bar;
  let number = near ? state.beatNumbers[p] : null;
  // If a downbeat is missing, the count would run on (8, 9, 10...): better show nothing
  if (number && perBar && number > perBar + 1) number = null;
  // The metronome light blinks on every beat while the click is on
  const blink = state.click && !audio.paused && p >= 0 && now - state.beats[p] < 0.12;
  $("led").classList.toggle("on", blink);
  $("led").classList.toggle("one", blink && number === 1);
  for (const square of document.querySelectorAll("#squares span")) {
    const on = Number(square.dataset.beat) === number;
    square.classList.toggle("on", on);
    square.classList.toggle("one", on && number === 1);
  }
  drawStrip(now);
  if (stemsPlaying()) moveLanePlayhead(now);
}

/** Scrolls only the grid (not the page) so that the bar being played is visible. */
function scrollGrid(cell) {
  const grid = $("bar-scroll");
  const top = cell.offsetTop;
  const bottom = top + cell.offsetHeight;
  if (top < grid.scrollTop || bottom > grid.scrollTop + grid.clientHeight) {
    grid.scrollTo({ top: Math.max(0, top - grid.clientHeight / 3), behavior: "smooth" });
  }
}

function ensureAudioContext() {
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!audioContext && Context) audioContext = new Context();
  if (audioContext && audioContext.state === "suspended") audioContext.resume();
}

// ---------------------------------------------------------------- pitch

/*
 * Browsers cannot change the pitch of an <audio> without changing its speed, so once the song
 * is moved, the players go through Web Audio and SoundTouch (an AudioWorklet), which moves the
 * pitch and keeps the tempo. The speed stays with the players (playbackRate keeps the pitch).
 * A player can be routed only once, so after that it stays routed, straight to the speakers
 * while the pitch is 0.
 */
const shifter = {
  node: null, // the SoundTouch node every player goes through while the song is moved
  loading: null,
  sources: new WeakMap(), // player -> its MediaElementAudioSourceNode
};

function loadShifter() {
  ensureAudioContext();
  if (!audioContext || !audioContext.audioWorklet || !window.AudioWorkletNode) {
    return Promise.reject(new Error("no AudioWorklet"));
  }
  shifter.loading ??= audioContext.audioWorklet.addModule("static/vendor/soundtouch/soundtouch-processor.js").then(() => {
    shifter.node = new AudioWorkletNode(audioContext, "soundtouch-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [2],
      processorOptions: { sampleBufferType: "circular" },
    });
    shifter.node.connect(audioContext.destination);
  });
  return shifter.loading;
}

/** Sends a player through the shifter while the song is moved, or straight out otherwise. */
function routeThroughShifter(player) {
  if (!shifter.node) return;
  let source = shifter.sources.get(player);
  if (!source) {
    source = audioContext.createMediaElementSource(player);
    shifter.sources.set(player, source);
  }
  source.disconnect();
  source.connect(state.pitch ? shifter.node : audioContext.destination);
}

function applyPitch() {
  if (!state.pitch && !shifter.node) return; // never moved: the players play on their own
  loadShifter()
    .then(() => {
      shifter.node.parameters.get("pitchSemitones").value = state.pitch;
      for (const player of [audio, ...Object.values(stems.players)]) routeThroughShifter(player);
    })
    .catch(() => {
      // An old browser: the names move, the sound cannot
      $("pitch-group").title = t("pitch_unsupported");
    });
}

function playClick(when, accent) {
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  oscillator.frequency.value = accent ? 1760 : 1100;
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(accent ? 0.5 : 0.3, when + 0.002);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
  oscillator.connect(gain).connect(audioContext.destination);
  oscillator.start(when);
  oscillator.stop(when + 0.06);
  pendingClicks.add(oscillator);
  oscillator.addEventListener("ended", () => pendingClicks.delete(oscillator));
}

/** Clicks are scheduled ~0.1 s ahead: on pause or seek the ones still to sound are cancelled. */
const pendingClicks = new Set();

function cancelClicks() {
  for (const oscillator of pendingClicks) {
    try {
      oscillator.stop();
    } catch {
      /* already finished */
    }
  }
  pendingClicks.clear();
}

function resetClicks() {
  cancelClicks();
  state.nextClick = search(state.beats, audio.currentTime - 0.001, null) + 1;
}

function scheduleClicks() {
  if (!state.click || audio.paused || audio.seeking || !audioContext) return;
  const now = audio.currentTime;
  const beats = state.beats;
  while (state.nextClick < beats.length && beats[state.nextClick] < now - 0.03) state.nextClick++;
  while (state.nextClick < beats.length && beats[state.nextClick] < now + 0.12) {
    const beat = beats[state.nextClick];
    const when = audioContext.currentTime + Math.max(0, (beat - now) / audio.playbackRate);
    playClick(when, state.downbeats.has(beat.toFixed(3)));
    state.nextClick++;
  }
}

let playbackTimer = null;

audio.addEventListener("play", () => {
  setPlayIcon(true);
  resetClicks();
  clearInterval(playbackTimer);
  playbackTimer = setInterval(() => {
    scheduleClicks();
    updatePlayback();
  }, 30);
});
audio.addEventListener("pause", () => {
  setPlayIcon(false);
  clearInterval(playbackTimer);
  cancelClicks();
  updatePlayback();
});
audio.addEventListener("seeking", cancelClicks);
audio.addEventListener("seeked", () => {
  resetClicks();
  updatePlayback();
});
audio.addEventListener("ratechange", resetClicks);
audio.addEventListener("error", () => {
  if (state.result && audio.getAttribute("src")) $("audio-error").hidden = false;
});

function stopPlayback() {
  audio.pause();
  clearInterval(playbackTimer);
  cancelClicks();
  audio.removeAttribute("src");
  audio.load();
  $("play").disabled = true;
  setPlayIcon(false);
}

// ---------------------------------------------------------------- stems (optional, issue #56)

/* The song can be split into vocals, drums, bass and the rest, each with its volume, mute and
   solo. The main <audio> keeps playing, muted, as the clock of the click and the grid; one
   <audio> per stem follows it. */
const STEM_NAMES = ["vocals", "drums", "bass", "other"];
// Hue of each track's lane, muted to sit on the warm background
const STEM_HUES = { vocals: 205, drums: 28, bass: 275, other: 160 };
const stems = {
  part: "start", // "start" | "progress" | "mixer" | "error"
  generation: 0, // bumped by every reset: late answers of an older request are ignored
  request: null, // the upload in flight
  job: null, // the separation running on the server
  error: null, // the message shown, kept to translate it again
  players: {},
  peaks: null, // each track's waveform, 0-100
  volume: {},
  muted: {},
  solo: null,
  timer: null,
};

function stemsPlaying() {
  return Object.keys(stems.players).length > 0;
}

/** The button only makes sense on a report, and while no separation is running or loaded. */
function updateSeparateButton() {
  $("separate").hidden = DEMO || $("report").hidden || stems.part === "progress" || stems.part === "mixer";
}

function showStems(part) {
  stems.part = part;
  if (part !== "error") stems.error = null;
  $("stems-section").hidden = part === "start";
  $("stems-progress").hidden = part !== "progress";
  $("stems-cancel").hidden = part !== "progress";
  $("stems-off").hidden = part !== "mixer";
  $("stems-rows").hidden = part !== "mixer";
  $("stems-error").hidden = part !== "error";
  if (part !== "progress") $("stems-step").textContent = "";
  updateSeparateButton();
}

function setStemsProgress(text, fraction) {
  $("stems-step").textContent = text;
  $("stems-fill").style.width = `${Math.max(0, Math.min(100, fraction * 100))}%`;
}

function stemsError(message) {
  stems.job = null;
  stems.request = null;
  showStems("error");
  stems.error = message;
  $("stems-error").textContent = messageText(message);
}

/** Back to the original mix, and cancels a separation that is still uploading or running. */
function resetStems() {
  stems.generation += 1;
  if (stems.request) stems.request.abort();
  stems.request = null;
  if (stems.job) fetch(`/api/separations/${stems.job}`, { method: "DELETE" }).catch(() => {});
  stems.job = null;
  clearInterval(stems.timer);
  for (const player of Object.values(stems.players)) {
    player.pause();
    player.removeAttribute("src");
    player.load();
  }
  stems.players = {};
  stems.peaks = null;
  stems.solo = null;
  $("stems-rows").replaceChildren();
  showStems("start");
  applyVolume();
}

$("separate").addEventListener("click", () => {
  if (!state.file) return;
  const generation = stems.generation;
  showStems("progress");
  setStemsProgress(t("uploading"), 0);
  const form = new FormData();
  form.append("file", state.file);
  const request = new XMLHttpRequest();
  stems.request = request;
  request.open("POST", "/api/separations");
  request.upload.addEventListener("progress", (e) => {
    if (generation !== stems.generation) return;
    if (e.lengthComputable) setStemsProgress(t("uploading_percent", { percent: percent(e.loaded / e.total) }), 0);
  });
  request.addEventListener("load", () => {
    let body = {};
    try {
      body = JSON.parse(request.responseText);
    } catch {
      /* empty response */
    }
    if (generation !== stems.generation) {
      // Cancelled after the upload had already reached the server: cancel the job too
      if (body.id) fetch(`/api/separations/${body.id}`, { method: "DELETE" }).catch(() => {});
      return;
    }
    stems.request = null;
    if (request.status === 200 && body.id) pollStems(body.id, generation);
    else stemsError(serverMessage(body.detail, request.status));
  });
  request.addEventListener("error", () => {
    if (generation === stems.generation) stemsError(local("connection_failed"));
  });
  request.send(form);
});

$("stems-cancel").addEventListener("click", resetStems);
$("stems-off").addEventListener("click", resetStems);

async function pollStems(id, generation) {
  stems.job = id;
  let failures = 0;
  while (stems.job === id && generation === stems.generation) {
    let job;
    try {
      const response = await fetch(`/api/separations/${id}`);
      job = await response.json();
      if (!response.ok) throw new Error(messageText(serverMessage(job.detail, response.status)));
      failures = 0;
    } catch (error) {
      if (++failures >= 5) {
        if (generation === stems.generation) stemsError(local("connection_lost", { detail: error.message }));
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    if (stems.job !== id || generation !== stems.generation) return; // cancelled meanwhile
    if (job.status === "done") {
      stems.job = null;
      loadStems(job.result);
      return;
    }
    if (job.status === "error") {
      stemsError(job.error);
      return;
    }
    setStemsProgress(`${t(job.step)}… ${percent(job.progress)}`, job.progress);
    await new Promise((r) => setTimeout(r, 1000));
  }
}

function loadStems(result) {
  const urls = result.stems;
  stems.peaks = null;
  if (result.peaks) {
    const generation = stems.generation;
    fetch(result.peaks)
      .then((response) => (response.ok ? response.json() : null))
      .then((peaks) => {
        if (peaks && generation === stems.generation) {
          stems.peaks = peaks;
          drawLanes();
        }
      })
      .catch(() => {});
  }
  for (const name of STEM_NAMES) {
    const player = new Audio(urls[name]);
    player.preload = "auto";
    stems.players[name] = player;
    routeThroughShifter(player);
    stems.volume[name] ??= 1;
    stems.muted[name] ??= false;
  }
  drawMixer();
  showStems("mixer");
  applyVolume(); // mutes the main player, which stays as the clock
  syncStems(true);
  clearInterval(stems.timer);
  stems.timer = setInterval(() => syncStems(false), 250);
}

/** Builds the rows; mute, solo and volume then only update them (keyboard focus stays put). */
function drawMixer() {
  $("stems-rows").replaceChildren(
    ...STEM_NAMES.map((name) => {
      const label = t(`stem_${name}`);
      const mute = el("button", { type: "button", class: "stem-mute", title: t("stem_mute"), "aria-label": `${t("stem_mute")}: ${label}` }, "M");
      const solo = el("button", { type: "button", class: "stem-solo", title: t("stem_solo"), "aria-label": `${t("stem_solo")}: ${label}` }, "S");
      const volume = el("input", { type: "range", min: "0", max: "100", step: "1", value: String(Math.round(stems.volume[name] * 100)), "aria-label": label });
      mute.addEventListener("click", () => {
        stems.muted[name] = !stems.muted[name];
        applyStemVolumes();
      });
      solo.addEventListener("click", () => {
        stems.solo = stems.solo === name ? null : name;
        applyStemVolumes();
      });
      volume.addEventListener("input", () => {
        stems.volume[name] = Number(volume.value) / 100;
        applyStemVolumes();
      });
      const lane = el("canvas", { class: "stem-lane", "aria-hidden": "true" });
      lane.addEventListener("click", (e) => {
        if (!state.result) return;
        const rect = lane.getBoundingClientRect();
        audio.currentTime = ((e.clientX - rect.left) / rect.width) * state.result.file.duration;
      });
      return el(
        "div",
        { class: "stem-row", "data-stem": name },
        el("div", { class: "stem-controls" }, el("span", { class: "stem-name" }, label), mute, solo, volume),
        lane
      );
    })
  );
  $("stems-rows").append(el("span", { class: "lanes-playhead", id: "lanes-playhead", "aria-hidden": "true" }));
  applyStemVolumes();
}

/** Draws each track's waveform in its lane, dimmed when the track is silent. */
function drawLanes() {
  for (const name of STEM_NAMES) {
    const row = document.querySelector(`.stem-row[data-stem="${name}"]`);
    if (!row) continue;
    const canvas = row.querySelector(".stem-lane");
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) continue;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const g = canvas.getContext("2d");
    g.scale(ratio, ratio);
    const hue = STEM_HUES[name];
    const silent = row.classList.contains("silent");
    g.fillStyle = `hsl(${hue}, ${silent ? 8 : 22}%, ${silent ? 18 : 24}%)`;
    g.fillRect(0, 0, width, height);
    const peaks = stems.peaks && stems.peaks[name];
    g.fillStyle = `hsl(${hue}, ${silent ? 10 : 45}%, ${silent ? 38 : 64}%)`;
    const middle = height / 2;
    if (!peaks) {
      g.fillRect(0, middle, width, 1);
      continue;
    }
    for (let x = 0; x < width; x++) {
      const from = Math.floor((x / width) * peaks.length);
      const to = Math.max(from + 1, Math.floor(((x + 1) / width) * peaks.length));
      let peak = 0;
      for (let i = from; i < to && i < peaks.length; i++) peak = Math.max(peak, peaks[i]);
      const half = Math.max(0.5, (peak / 100) * (middle - 2));
      g.fillRect(x, middle - half, 1, half * 2);
    }
  }
  moveLanePlayhead(audio.currentTime);
}

/** The vertical line that marks the time across every lane. */
function moveLanePlayhead(now) {
  const line = $("lanes-playhead");
  const lane = document.querySelector(".stem-lane");
  if (!line || !lane || !state.result) return;
  const box = $("stems-rows").getBoundingClientRect();
  const rect = lane.getBoundingClientRect();
  const fraction = Math.max(0, Math.min(1, now / state.result.file.duration));
  line.style.left = `${rect.left - box.left + fraction * rect.width}px`;
}

window.addEventListener("resize", () => {
  if (stemsPlaying()) drawLanes();
});

/**
 * Silencing uses `muted`, which every browser honours; the level uses `volume`, which iOS
 * ignores (there the hardware buttons set it).
 */
function applyStemVolumes() {
  for (const [name, player] of Object.entries(stems.players)) {
    const audible = stems.solo ? stems.solo === name : !stems.muted[name];
    player.muted = !audible || songVolume() === 0;
    player.volume = stems.volume[name] * state.volume;
    const row = document.querySelector(`.stem-row[data-stem="${name}"]`);
    if (!row) continue;
    row.classList.toggle("silent", !audible);
    row.querySelector(".stem-mute").setAttribute("aria-pressed", String(stems.muted[name]));
    row.querySelector(".stem-solo").setAttribute("aria-pressed", String(stems.solo === name));
  }
  if (stemsPlaying()) drawLanes();
}

/** Keeps every stem on the main player's time, speed and play/pause state. */
function syncStems(force) {
  for (const player of Object.values(stems.players)) {
    player.playbackRate = audio.playbackRate;
    if (!player.seeking && (force || Math.abs(player.currentTime - audio.currentTime) > 0.06)) {
      player.currentTime = audio.currentTime;
    }
    if (audio.paused && !player.paused) player.pause();
    else if (!audio.paused && player.paused) player.play().catch(() => {});
  }
}

for (const event of ["play", "pause", "seeked", "ratechange"]) {
  audio.addEventListener(event, () => {
    if (stemsPlaying()) syncStems(true);
  });
}

// ---------------------------------------------------------------- online demo

/** The demo has no server: it opens one song that is already analyzed (see demo/README.md). */
async function startDemo() {
  $("new-analysis").hidden = true;
  $("install").hidden = false;
  $("demo-bar").hidden = false;
  drawDemoBar();
  try {
    const response = await fetch(DEMO.result);
    if (!response.ok) throw new Error(String(response.status));
    const result = await response.json();
    state.url = DEMO.audio;
    state.title = `${DEMO.title} – ${DEMO.author}`;
    showReport(result);
  } catch {
    showError(local("demo_failed"));
  }
}

/** Says that this is a demo, credits the song (its licence asks for it) and links to the install. */
function drawDemoBar() {
  const link = (href, text) => el("a", { href, target: "_blank", rel: "noopener" }, text);
  $("demo-bar").replaceChildren(
    el("span", { class: "demo-badge" }, t("demo_badge")),
    el("span", { class: "demo-credit" },
      t("demo_credit", { title: DEMO.title, author: DEMO.author }), " (",
      link(DEMO.source, "incompetech.com"), ", ", link(DEMO.licenseUrl, DEMO.license), ")"),
    link("https://github.com/joaquinmuzzi/Tonos#installation", `${t("demo_install")} →`),
  );
}

// ---------------------------------------------------------------- volume

/** The song's volume (0..1): the slider, or 0 while the speaker button is off. */
function songVolume() {
  return state.volumeOff ? 0 : state.volume;
}

/** Applies the volume to the song and, when they play, to the separated tracks. */
function applyVolume() {
  audio.volume = state.volume;
  audio.muted = stemsPlaying() || songVolume() === 0;
  applyStemVolumes();
  const silent = songVolume() === 0;
  $("volume").value = String(Math.round(state.volume * 100));
  $("volume-mute").setAttribute("aria-pressed", String(state.volumeOff));
  $("volume-group").classList.toggle("off", silent);
}

$("volume").addEventListener("input", () => {
  state.volume = Number($("volume").value) / 100;
  state.volumeOff = false;
  savePreference("volume", String(state.volume));
  applyVolume();
});
$("volume-mute").addEventListener("click", () => {
  state.volumeOff = !state.volumeOff;
  applyVolume();
});

translatePage();
markButtons();
applyVolume();
if (DEMO) startDemo();
