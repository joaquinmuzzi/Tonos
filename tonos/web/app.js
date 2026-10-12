"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  result: null,
  url: null, // local URL of the chosen file, to play it without uploading it again
  notation: readPreference("notation", language === "es" ? "solfege" : "letter"),
  detail: readPreference("detail", "simple"),
  beats: [],
  beatNumbers: [], // number of each beat within its bar (1 = downbeat)
  downbeats: new Set(),
  activeBar: -1,
  nextClick: 0,
  timer: null,
  error: null, // message shown in the error box, kept to translate it again
};

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

/** Like parent.append(), but skips nulls (append would show them as the text "null"). */
function appendAll(parent, ...children) {
  parent.append(...children.filter((c) => c !== null && c !== undefined && c !== false));
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

function badge(confidence) {
  if (!["high", "medium", "low"].includes(confidence)) return null;
  return el("span", { class: `badge ${confidence}` }, t(`confidence_${confidence}`));
}

function show(section) {
  for (const id of ["upload", "progress", "error", "report"]) $(id).hidden = id !== section;
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
$("another").addEventListener("click", () => {
  stopPlayback();
  state.result = null;
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

function showReport(result) {
  state.result = result;
  state.beats = result.beats;
  state.downbeats = new Set(result.downbeats.map((time) => time.toFixed(3)));
  state.beatNumbers = numberBeats(result);
  state.activeBar = -1;

  $("file-name").textContent = result.file.name;
  $("duration").textContent = mmss(result.file.duration);
  $("cached").hidden = !result.from_cache;
  $("audio-error").hidden = true;
  audio.src = state.url;

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

/** Draws every card. Called again when the notation or the chord detail changes. */
function drawReport() {
  drawTempo(state.result.tempo);
  drawMeter(state.result.meter);
  drawKey(state.result.key, state.result.tuning);
  drawChords();
  state.activeBar = -1;
  updatePlayback();
}

function secondTempoMethodText(second) {
  const bpm = rounded(second.bpm);
  const known = ["same", "double", "half", "triple", "third"].includes(second.relation);
  return t(known ? `tempo_${second.relation}` : "tempo_mismatch", { bpm });
}

function tempoCurve(curve, duration) {
  if (!curve || curve.length < 2) return null;
  const values = curve.map(([, b]) => b);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (max - min < 8) {
    min = mean - 4;
    max = mean + 4;
  }
  const width = 300;
  const height = 60;
  const points = curve
    .map(([time, bpm]) => `${((time / duration) * width).toFixed(1)},${(height - 6 - ((bpm - min) / (max - min)) * (height - 12)).toFixed(1)}`)
    .join(" ");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("class", "tempo-curve");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    t("tempo_curve_label", { min: rounded(Math.min(...values)), max: rounded(Math.max(...values)) })
  );
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", points);
  svg.append(line);
  return el("div", {}, el("p", { class: "muted" }, t("tempo_curve_title")), svg);
}

function drawTempo(tempo) {
  const card = $("tempo-card");
  card.replaceChildren(el("h2", {}, t("tempo_title")));
  if (!tempo.bpm) {
    appendAll(card, el("p", { class: "big" }, "—"), el("p", {}, messageText(tempo.reason)), badge("low"));
    return;
  }
  const alt = tempo.alternatives;
  appendAll(
    card,
    el("p", { class: "big" }, rounded(tempo.bpm), el("span", { class: "unit" }, " BPM")),
    badge(tempo.confidence),
    tempo.suggestion
      ? el("p", { class: "highlight" }, t("tempo_suggestion", { bpm: rounded(alt[tempo.suggestion]) }))
      : null,
    el("p", {}, t("tempo_double_half", { double: rounded(alt.double), half: rounded(alt.half) })),
    el(
      "p",
      {},
      tempo.stable ? t("tempo_stable") : t("tempo_varies", { min: rounded(tempo.range[0]), max: rounded(tempo.range[1]) })
    ),
    tempo.regularity < 0.7 ? el("p", { class: "warning" }, t("tempo_irregular")) : null,
    tempo.warning ? el("p", { class: "warning" }, messageText(tempo.warning)) : null,
    el("p", { class: "muted" }, secondTempoMethodText(tempo.second_method)),
    tempoCurve(tempo.curve, state.result.file.duration)
  );
}

function meterReading(meter) {
  if (!meter.time_signature) return t("meter_beats_per_bar", { beats: meter.beats_per_bar });
  return meter.swing ? t("meter_swing", { signature: meter.time_signature }) : meter.time_signature;
}

function drawMeter(meter) {
  const card = $("meter-card");
  card.replaceChildren(el("h2", {}, t("meter_title")));
  if (!meter.beats_per_bar) {
    appendAll(card, el("p", { class: "big" }, "—"), badge("low"), el("p", {}, messageText(meter.reason)));
    return;
  }
  const source =
    meter.source === "periodicity"
      ? t("meter_source_periodicity", { beats: meter.beats_per_bar })
      : t("meter_source_downbeats", {
          beats: meter.beats_per_bar,
          percent: percent(meter.agreement),
          bars: meter.bars_counted,
        });
  appendAll(
    card,
    el("p", { class: "big" }, meterReading(meter)),
    meter.alternative ? el("p", { class: "muted" }, messageText(meter.alternative)) : null,
    badge(meter.confidence),
    el("p", {}, source),
    meter.second_method && meter.second_method.confirms ? el("p", { class: "muted" }, t("meter_confirmed")) : null,
    el("p", {}, t(`subdivision_${meter.subdivision.kind}`)),
    ...meter.warnings.map((w) => el("p", { class: "warning" }, messageText(w)))
  );
}

/** "Sol mayor", "G mayor"... in the chosen notation. */
function keyName(key, notation = state.notation) {
  return t("key_name", { tonic: key[notation], mode: t(key.mode) });
}

function drawKey(key, tuning) {
  const other = state.notation === "solfege" ? "letter" : "solfege";
  const card = $("key-card");
  card.replaceChildren();
  appendAll(
    card,
    el("h2", {}, t("key_title")),
    el("p", { class: "big" }, keyName(key.best)),
    el("p", { class: "muted" }, `(${keyName(key.best, other)})`),
    badge(key.confidence)
  );
  const alternatives = key.alternatives.map((a) => `${keyName(a)} (${t(`key_reason_${a.reason}`)})`);
  appendAll(card, el("p", {}, t("key_alternatives", { keys: alternatives.join(", ") })));

  const second = key.second_method;
  if (second) {
    appendAll(card, el("p", { class: "muted" }, t(`key_chords_${second.agreement}`, { key: keyName(second) })));
  }
  for (const change of key.sections.changes) {
    appendAll(
      card,
      el(
        "p",
        { class: "warning" },
        t("key_change", { start: mmss(change.start), end: mmss(change.end), key: keyName(change) })
      )
    );
  }
  if (tuning.warning) appendAll(card, el("p", { class: "warning" }, messageText(tuning.warning)));
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

function drawChords() {
  const chords = state.result.chords;
  const summary = state.detail === "simple" ? chords.summary_simple : chords.summary;
  $("grid-note").textContent = t(state.result.meter.approximate_grid ? "grid_note_approximate" : "grid_note");
  $("chords-note").textContent = t(state.detail === "simple" ? "chords_note_simple" : "chords_note_full");
  $("chord-summary").replaceChildren(
    ...summary.map((a) => el("span", { class: "chip" }, a[state.notation], el("span", {}, percent(a.share))))
  );
  if (!summary.length) $("chord-summary").append(el("p", { class: "muted" }, t("no_chords")));

  const cells = state.result.bars.map((bar, i) =>
    el(
      "button",
      {
        type: "button",
        class: "bar-cell",
        "data-i": String(i),
        title: t("listen_from", { time: mmss(bar.start) }),
        onclick: () => {
          audio.currentTime = bar.start;
          audio.play().catch(() => {});
        },
      },
      el("span", { class: "num" }, barLabel(bar)),
      el("span", { class: "chord-names" }, chordsOfBar(bar))
    )
  );
  $("bar-grid").replaceChildren(...cells);
  if (!cells.length) $("bar-grid").append(el("p", { class: "muted" }, t("no_bars")));
}

// ---------------------------------------------------------------- language and notation

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

// ---------------------------------------------------------------- playback

function updatePlayback() {
  if (!state.result) return;
  const now = audio.currentTime;
  const segments = state.result.chords.segments;

  const i = search(segments, now);
  const current = i >= 0 && now < segments[i].end ? segments[i] : null;
  $("current-chord").textContent = chordName(current);
  let next = null;
  for (let j = i + 1; j < segments.length; j++) {
    if (segments[j].is_chord && chordName(segments[j]) !== chordName(current)) {
      next = segments[j];
      break;
    }
  }
  $("next-chord").textContent = chordName(next);

  const bars = state.result.bars;
  const k = search(bars, now);
  const bar = k >= 0 && now < bars[k].end ? bars[k] : null;
  $("current-bar").textContent = bar ? barLabel(bar) : "—";
  if (k !== state.activeBar) {
    $("bar-grid").querySelector(".bar-cell.active")?.classList.remove("active");
    const cell = $("bar-grid").querySelector(`.bar-cell[data-i="${k}"]`);
    if (cell) {
      cell.classList.add("active");
      if ($("follow").checked && !audio.paused) scrollGrid(cell);
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
}

/** Scrolls only the grid (not the page) so that the bar being played is visible. */
function scrollGrid(cell) {
  const grid = $("bar-grid");
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
  if (!$("click").checked || audio.paused || audio.seeking || !audioContext) return;
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
  if ($("click").checked) ensureAudioContext();
  resetClicks();
  clearInterval(playbackTimer);
  playbackTimer = setInterval(() => {
    scheduleClicks();
    updatePlayback();
  }, 30);
});
audio.addEventListener("pause", () => {
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

$("click").addEventListener("change", () => {
  if ($("click").checked) ensureAudioContext();
  resetClicks();
});

function stopPlayback() {
  audio.pause();
  clearInterval(playbackTimer);
  cancelClicks();
  audio.removeAttribute("src");
  audio.load();
}

translatePage();
markButtons();
