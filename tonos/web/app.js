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
};

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5];
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
}

/**
 * Colour of a chord: the hue follows the circle of fifths from its root, so chords a fifth apart
 * get neighbouring colours (C, G, D...). Minor chords are darker; no chord is gray.
 */
function chordColor(segment) {
  if (!segment || !segment.is_chord || segment.root_pc === null) return "#3a352f";
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
  state.beats = result.beats;
  state.downbeats = new Set(result.downbeats.map((time) => time.toFixed(3)));
  state.beatNumbers = numberBeats(result);
  state.activeBar = -1;

  $("audio-error").hidden = true;
  if (!Object.keys(stems.players).length && !stems.job) showStems("start");
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

/** "Do", "C"... in the chosen notation. */
function tonicName(key, notation = state.notation) {
  return key[notation];
}

function keyName(key, notation = state.notation) {
  return t("key_name", { tonic: key[notation], mode: t(key.mode) });
}

function drawKey(key) {
  const best = key.best;
  const scale = best.scale ? best.scale[state.notation].join(" ") : "";
  stat(
    "key-stat",
    t("key_title"),
    el("div", { class: "value" }, tonicName(best), el("small", {}, ` ${t(best.mode)}`)),
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

function chordName(segment) {
  if (!segment) return "—";
  return segment[state.detail === "simple" ? `${state.notation}_simple` : state.notation];
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
}

function setLanguage(code) {
  language = code;
  savePreference("language", code);
  translatePage();
  markButtons();
  if (state.error) $("error-text").textContent = messageText(state.error);
  if (state.result) drawReport();
  if (DEMO) drawDemoBar();
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

function play() {
  ensureAudioContext();
  connectMain();
  audio.play().catch(() => {});
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

// ---------------------------------------------------------------- level meters

/* What is heard goes through Web Audio, so its level can be measured: the main player into a
   master analyser, and each stem through its own volume (a gain) and analyser into the same
   master. Without Web Audio the page plays as before, without meters. */
const METER_FLOOR = -48; // dBFS shown as an empty meter
const levels = { master: null, mainSource: null, frame: 0, shown: new Map() };

function connectMain() {
  if (levels.master || !audioContext) return;
  try {
    levels.master = audioContext.createAnalyser();
    levels.master.fftSize = 1024;
    levels.master.connect(audioContext.destination);
    levels.mainSource = audioContext.createMediaElementSource(audio);
    levels.mainSource.connect(levels.master);
  } catch {
    levels.master = null; // the audio keeps playing straight to the speakers
  }
}

/** Level in dBFS (RMS) of what an analyser hears now. */
function levelOf(analyser) {
  const data = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(data);
  let sum = 0;
  for (const x of data) sum += x * x;
  return 10 * Math.log10(sum / data.length + 1e-12);
}

/** Moves a meter's bar: it rises at once and falls slowly, like a VU meter. */
function showLevel(meter, db) {
  const fill = meter.firstElementChild;
  const previous = levels.shown.get(meter) ?? METER_FLOOR;
  const shown = Math.max(db, previous - 1.2); // ~70 dB/s at 60 frames per second
  levels.shown.set(meter, shown);
  const fraction = Math.max(0, Math.min(1, (shown - METER_FLOOR) / -METER_FLOOR));
  fill.style.width = `${fraction * 100}%`;
  meter.classList.toggle("hot", shown > -6);
  return shown > METER_FLOOR + 0.5;
}

function drawLevels() {
  levels.frame = 0;
  let moving = false;
  if (levels.master) moving = showLevel($("master-meter"), levelOf(levels.master)) || moving;
  for (const [name, node] of Object.entries(stems.nodes)) {
    const meter = document.querySelector(`.stem-row[data-stem="${name}"] .meter`);
    if (meter) moving = showLevel(meter, levelOf(node.analyser)) || moving;
  }
  // Keeps drawing while something plays, and until the bars have fallen after a pause
  if (moving || !audio.paused) levels.frame = requestAnimationFrame(drawLevels);
}

function startLevels() {
  if (!levels.frame) levels.frame = requestAnimationFrame(drawLevels);
}

audio.addEventListener("play", startLevels);

// ---------------------------------------------------------------- stems (optional, issue #56)

/* The song can be split into vocals, drums, bass and the rest, each with its volume, mute and
   solo. The main <audio> keeps playing, muted, as the clock of the click and the grid; one
   <audio> per stem follows it. */
const STEM_NAMES = ["vocals", "drums", "bass", "other"];
const stems = { job: null, players: {}, nodes: {}, volume: {}, muted: {}, solo: null, timer: null };

/** "start": only the button; "progress": separating; "mixer": the tracks; "error": the message. */
function showStems(part) {
  $("separate").hidden = DEMO || !state.result || part === "progress" || part === "mixer";
  $("stems-section").hidden = part === "start";
  $("stems-progress").hidden = part !== "progress";
  $("stems-cancel").hidden = part !== "progress";
  $("stems-off").hidden = part !== "mixer";
  $("stems-rows").hidden = part !== "mixer";
  $("stems-error").hidden = part !== "error";
  if (part !== "progress") $("stems-step").textContent = "";
}

function setStemsProgress(text, fraction) {
  $("stems-step").textContent = text;
  $("stems-fill").style.width = `${Math.max(0, Math.min(100, fraction * 100))}%`;
}

function stemsError(message) {
  stems.job = null;
  showStems("error");
  $("stems-error").textContent = messageText(message);
}

/** Back to the original mix, and cancels a separation that is still running. */
function resetStems() {
  if (stems.job) fetch(`/api/separations/${stems.job}`, { method: "DELETE" }).catch(() => {});
  stems.job = null;
  clearInterval(stems.timer);
  for (const player of Object.values(stems.players)) {
    player.pause();
    player.removeAttribute("src");
    player.load();
  }
  for (const node of Object.values(stems.nodes)) {
    node.source.disconnect();
    node.analyser.disconnect();
  }
  stems.players = {};
  stems.nodes = {};
  stems.solo = null;
  audio.muted = false;
  showStems("start");
}

$("separate").addEventListener("click", () => {
  if (!state.file) return;
  showStems("progress");
  setStemsProgress(t("uploading"), 0);
  const form = new FormData();
  form.append("file", state.file);
  const request = new XMLHttpRequest();
  request.open("POST", "/api/separations");
  request.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) setStemsProgress(t("uploading_percent", { percent: percent(e.loaded / e.total) }), 0);
  });
  request.addEventListener("load", () => {
    let body = {};
    try {
      body = JSON.parse(request.responseText);
    } catch {
      /* empty response */
    }
    if (request.status === 200 && body.id) pollStems(body.id);
    else stemsError(serverMessage(body.detail, request.status));
  });
  request.addEventListener("error", () => stemsError(local("connection_failed")));
  request.send(form);
});

$("stems-cancel").addEventListener("click", resetStems);
$("stems-off").addEventListener("click", resetStems);

async function pollStems(id) {
  stems.job = id;
  let failures = 0;
  while (stems.job === id) {
    let job;
    try {
      const response = await fetch(`/api/separations/${id}`);
      job = await response.json();
      if (!response.ok) throw new Error(messageText(serverMessage(job.detail, response.status)));
      failures = 0;
    } catch (error) {
      if (++failures >= 5) {
        stemsError(local("connection_lost", { detail: error.message }));
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    if (stems.job !== id) return; // cancelled meanwhile
    if (job.status === "done") {
      stems.job = null;
      loadStems(job.result.stems);
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

function connectStem(name, player) {
  ensureAudioContext();
  connectMain();
  if (!levels.master) return; // no Web Audio: the element's own volume is used
  try {
    const source = audioContext.createMediaElementSource(player);
    const gain = audioContext.createGain();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(gain).connect(analyser).connect(levels.master);
    stems.nodes[name] = { source, gain, analyser };
  } catch {
    /* plays without its meter */
  }
}

function loadStems(urls) {
  for (const name of STEM_NAMES) {
    const player = new Audio(urls[name]);
    player.preload = "auto";
    stems.players[name] = player;
    connectStem(name, player);
    stems.volume[name] ??= 1;
    stems.muted[name] ??= false;
  }
  audio.muted = true;
  drawMixer();
  showStems("mixer");
  syncStems(true);
  clearInterval(stems.timer);
  stems.timer = setInterval(() => syncStems(false), 250);
}

function drawMixer() {
  $("stems-rows").replaceChildren(
    ...STEM_NAMES.map((name) => {
      const mute = el("button", { type: "button", class: "stem-mute", title: t("stem_mute"), "aria-pressed": String(stems.muted[name]) }, "M");
      const solo = el("button", { type: "button", class: "stem-solo", title: t("stem_solo"), "aria-pressed": String(stems.solo === name) }, "S");
      const volume = el("input", { type: "range", min: "0", max: "100", value: String(Math.round(stems.volume[name] * 100)), "aria-label": t(`stem_${name}`) });
      mute.addEventListener("click", () => {
        stems.muted[name] = !stems.muted[name];
        drawMixer();
      });
      solo.addEventListener("click", () => {
        stems.solo = stems.solo === name ? null : name;
        drawMixer();
      });
      volume.addEventListener("input", () => {
        stems.volume[name] = Number(volume.value) / 100;
        applyStemVolumes();
      });
      const meter = el("span", { class: "meter", "aria-hidden": "true" }, el("span"));
      return el("div", { class: "stem-row", "data-stem": name }, el("span", { class: "stem-name" }, t(`stem_${name}`)), mute, solo, volume, meter);
    })
  );
  applyStemVolumes();
}

function applyStemVolumes() {
  for (const [name, player] of Object.entries(stems.players)) {
    const audible = stems.solo ? stems.solo === name : !stems.muted[name];
    const volume = audible ? stems.volume[name] : 0;
    if (stems.nodes[name]) stems.nodes[name].gain.gain.value = volume;
    else player.volume = volume;
    document.querySelector(`.stem-row[data-stem="${name}"]`)?.classList.toggle("silent", !audible);
  }
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
    if (Object.keys(stems.players).length) syncStems(true);
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

translatePage();
markButtons();
if (DEMO) startDemo();
