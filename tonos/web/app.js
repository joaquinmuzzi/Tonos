"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  result: null,
  url: null, // local URL of the chosen file, to play it without uploading it again
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
};

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5];
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
  if (!segment || !segment.is_chord || segment.root_pc === null) return "#2a2a2a";
  const hue = ((segment.root_pc * 7) % 12) * 30;
  const minor = /m(?!aj)/.test(segment.letter_simple || "");
  return `hsl(${hue}, ${minor ? 55 : 70}%, ${minor ? 42 : 56}%)`;
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
  if (!$("progress").hidden) return; // an analysis is already running
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

$("retry").addEventListener("click", () => show("upload"));
$("new-analysis").addEventListener("click", () => {
  stopPlayback();
  state.result = null;
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
      g.fillStyle = "#050505";
      g.fillRect(left - 1, 0, 2, height);
    }
  }
  g.globalAlpha = 1;
  if (current >= 0) {
    const left = x(beats[current]);
    const right = current + 1 < beats.length ? x(beats[current + 1]) : left + 3;
    g.strokeStyle = "#ededed";
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
  if (state.click) ensureAudioContext();
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
    state.result.file.name.replace(/\.[^.]+$/, ""),
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
  const count = $("beat-count");
  count.textContent = number ? String(number) : "";
  count.classList.toggle("downbeat", number === 1);
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
  $("beat-count").textContent = "";
}

translatePage();
markButtons();
