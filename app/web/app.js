"use strict";

const $ = (id) => document.getElementById(id);

const estado = {
  resultado: null,
  url: null, // URL local del archivo elegido, para reproducirlo sin volver a subirlo
  notacion: leerPreferencia("notacion", "latino"),
  detalle: leerPreferencia("detalle", "simple"),
  pulsos: [],
  numeros: [], // número de pulso dentro del compás (1 = primer tiempo)
  primeros: new Set(),
  compasActivo: -1,
  proximoClic: 0,
  reloj: null,
};

const audio = $("audio");
let contextoAudio = null;

// ---------------------------------------------------------------- utilidades

function leerPreferencia(clave, porDefecto) {
  try {
    return localStorage.getItem("analizador-" + clave) || porDefecto;
  } catch {
    return porDefecto;
  }
}

function guardarPreferencia(clave, valor) {
  try {
    localStorage.setItem("analizador-" + clave, valor);
  } catch {
    /* sin almacenamiento: no pasa nada */
  }
}

/** Crea un elemento. Los textos van como textContent (nunca como HTML). */
function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (clave === "class") nodo.className = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else nodo.setAttribute(clave, valor);
  }
  for (const hijo of hijos) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : String(hijo));
  }
  return nodo;
}

/** Como padre.append(), pero ignora los null (append los mostraría como el texto "null"). */
function anexar(padre, ...hijos) {
  padre.append(...hijos.filter((h) => h !== null && h !== undefined && h !== false));
}

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const porcentaje = (x) => `${Math.round(x * 100)} %`;
const redondo = (x) => String(Math.round(x));

/** Último índice i tal que lista[i][clave] <= t (o -1). */
function buscar(lista, t, clave = "inicio") {
  let bajo = 0;
  let alto = lista.length - 1;
  let respuesta = -1;
  while (bajo <= alto) {
    const medio = (bajo + alto) >> 1;
    const valor = clave ? lista[medio][clave] : lista[medio];
    if (valor <= t) {
      respuesta = medio;
      bajo = medio + 1;
    } else {
      alto = medio - 1;
    }
  }
  return respuesta;
}

function insignia(confianza) {
  const texto = { alta: "Confianza alta", media: "Confianza media", baja: "Confianza baja" }[confianza];
  return texto ? el("span", { class: `insignia ${confianza}` }, texto) : null;
}

function mostrar(seccion) {
  for (const id of ["subida", "progreso", "error", "reporte"]) $(id).hidden = id !== seccion;
}

// ---------------------------------------------------------------- subida

const zona = $("zona");
const entrada = $("archivo");

entrada.addEventListener("change", () => {
  if (entrada.files.length) subir(entrada.files[0]);
  entrada.value = "";
});
zona.addEventListener("dragover", () => zona.classList.add("encima"));
zona.addEventListener("dragleave", () => zona.classList.remove("encima"));
// Se aceptan archivos soltados en cualquier parte de la página (también sobre un reporte,
// para analizar otra canción). Sin esto, el navegador abriría el archivo y se perdería todo.
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  zona.classList.remove("encima");
  if (!$("progreso").hidden) return; // ya hay un análisis en curso
  if (e.dataTransfer && e.dataTransfer.files.length) subir(e.dataTransfer.files[0]);
});

const TAMANO_MAXIMO = 1024 ** 3;

function ponerProgreso(texto, fraccion) {
  $("paso").textContent = texto;
  const valor = Math.max(0, Math.min(100, fraccion * 100));
  $("barra-relleno").style.width = `${valor}%`;
  $("barra").setAttribute("aria-valuenow", String(Math.round(valor)));
}

function subir(archivo) {
  if (archivo.size > TAMANO_MAXIMO) {
    mostrarError("El archivo es demasiado grande (máximo 1 GB). Si es un video, probá con una versión más liviana o solo con el audio.");
    return;
  }
  detenerReproduccion();
  estado.resultado = null;
  if (estado.url) URL.revokeObjectURL(estado.url);
  estado.url = URL.createObjectURL(archivo);

  mostrar("progreso");
  ponerProgreso("Subiendo el archivo…", 0);
  const inicio = performance.now();
  clearInterval(estado.reloj);
  estado.reloj = setInterval(() => {
    $("tiempo").textContent = `${Math.round((performance.now() - inicio) / 1000)} s`;
  }, 500);

  const datos = new FormData();
  datos.append("archivo", archivo);
  const pedido = new XMLHttpRequest();
  pedido.open("POST", "/api/analisis");
  pedido.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      ponerProgreso(`Subiendo el archivo… ${porcentaje(e.loaded / e.total)}`, 0.02 * (e.loaded / e.total));
    }
  });
  pedido.addEventListener("load", () => {
    let cuerpo = {};
    try {
      cuerpo = JSON.parse(pedido.responseText);
    } catch {
      /* respuesta vacía */
    }
    if (pedido.status === 200 && cuerpo.id) consultar(cuerpo.id);
    else mostrarError(cuerpo.detail || `El servidor respondió con un error (${pedido.status}).`);
  });
  pedido.addEventListener("error", () =>
    mostrarError("No me pude conectar con el analizador. ¿Sigue abierta su ventana?")
  );
  pedido.send(datos);
}

async function consultar(id) {
  let fallos = 0;
  for (;;) {
    let trabajo;
    try {
      const respuesta = await fetch(`/api/analisis/${id}`);
      trabajo = await respuesta.json();
      if (!respuesta.ok) throw new Error(trabajo.detail || "Error del servidor");
      fallos = 0;
    } catch (error) {
      if (++fallos >= 5) {
        mostrarError(`Perdí la conexión con el analizador: ${error.message}`);
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    if (trabajo.estado === "listo") {
      clearInterval(estado.reloj);
      mostrarReporte(trabajo.resultado);
      return;
    }
    if (trabajo.estado === "error") {
      mostrarError(trabajo.error);
      return;
    }
    ponerProgreso(`${trabajo.paso}…`, trabajo.progreso);
    await new Promise((r) => setTimeout(r, 600));
  }
}

function mostrarError(mensaje) {
  clearInterval(estado.reloj);
  $("error-texto").textContent = mensaje;
  mostrar("error");
}

$("reintentar").addEventListener("click", () => mostrar("subida"));
$("otra").addEventListener("click", () => {
  detenerReproduccion();
  estado.resultado = null;
  mostrar("subida");
  window.scrollTo({ top: 0 });
});

$("descargar").addEventListener("click", () => {
  if (!estado.resultado) return;
  const blob = new Blob([JSON.stringify(estado.resultado, null, 2)], { type: "application/json" });
  const enlace = el("a", { href: URL.createObjectURL(blob), download: `${estado.resultado.archivo.nombre}.analisis.json` });
  document.body.append(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(enlace.href), 1000);
});

// ---------------------------------------------------------------- reporte

function mostrarReporte(resultado) {
  estado.resultado = resultado;
  estado.pulsos = resultado.pulsos;
  estado.primeros = new Set(resultado.primeros_tiempos.map((t) => t.toFixed(3)));
  estado.numeros = numerarPulsos(resultado);
  estado.compasActivo = -1;

  $("nombre-archivo").textContent = resultado.archivo.nombre;
  $("duracion").textContent = mmss(resultado.archivo.duracion);
  $("cache").hidden = !resultado.desde_cache;
  $("audio-error").hidden = true;
  audio.src = estado.url;

  marcarBotones();
  dibujarTempo(resultado.tempo);
  dibujarCompas(resultado.compas);
  dibujarNombres();
  mostrar("reporte");
  actualizarReproduccion();
}

/** Número de cada pulso dentro de su compás (1 = primer tiempo). */
function numerarPulsos(resultado) {
  const porCompas = resultado.compas.pulsos_por_compas;
  const primero = resultado.primeros_tiempos.length ? resultado.primeros_tiempos[0] : Infinity;
  const anacrusa = resultado.pulsos.filter((t) => t < primero).length;
  let contador = 0;
  return resultado.pulsos.map((t, i) => {
    if (estado.primeros.has(t.toFixed(3))) contador = 1;
    else if (contador > 0) contador += 1;
    // Antes del primer primer-tiempo (anacrusa): se cuentan los últimos pulsos del compás
    else return porCompas && anacrusa < porCompas ? porCompas - anacrusa + i + 1 : null;
    return contador;
  });
}

/** Lo que depende de la notación elegida se vuelve a dibujar al cambiarla. */
function dibujarNombres() {
  dibujarTonalidad(estado.resultado.tonalidad, estado.resultado.afinacion);
  dibujarAcordes();
  estado.compasActivo = -1;
  actualizarReproduccion();
}

function textoSegundoMetodo(segundo) {
  const bpm = redondo(segundo.bpm);
  switch (segundo.relacion) {
    case "igual":
      return `Un segundo método independiente da casi lo mismo (${bpm} BPM).`;
    case "doble":
    case "mitad":
      return `Un segundo método da ${bpm} BPM (${segundo.relacion === "doble" ? "el doble" : "la mitad"}): es la ambigüedad típica del tempo.`;
    case "triple":
    case "tercio":
      return `Un segundo método da ${bpm} BPM (${segundo.relacion === "triple" ? "el triple" : "un tercio"}): suele pasar cuando el pulso se divide en tres.`;
    default:
      return `Un segundo método da ${bpm} BPM, que no coincide: tomá el tempo con cuidado.`;
  }
}

function curvaDeTempo(curva, duracion) {
  if (!curva || curva.length < 2) return null;
  const valores = curva.map(([, b]) => b);
  const promedio = valores.reduce((a, b) => a + b, 0) / valores.length;
  let minimo = Math.min(...valores);
  let maximo = Math.max(...valores);
  if (maximo - minimo < 8) {
    minimo = promedio - 4;
    maximo = promedio + 4;
  }
  const ancho = 300;
  const alto = 60;
  const puntos = curva
    .map(([t, b]) => `${((t / duracion) * ancho).toFixed(1)},${(alto - 6 - ((b - minimo) / (maximo - minimo)) * (alto - 12)).toFixed(1)}`)
    .join(" ");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("class", "curva");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Tempo a lo largo de la canción, entre ${redondo(Math.min(...valores))} y ${redondo(Math.max(...valores))} BPM`);
  const linea = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  linea.setAttribute("points", puntos);
  svg.append(linea);
  return el("div", {}, el("p", { class: "tenue" }, "Tempo a lo largo de la canción:"), svg);
}

function dibujarTempo(t) {
  const tarjeta = $("t-tempo");
  tarjeta.replaceChildren(el("h2", {}, "Tempo"));
  if (!t.bpm) {
    anexar(tarjeta, el("p", { class: "grande" }, "—"), el("p", {}, t.motivo), insignia("baja"));
    return;
  }
  anexar(tarjeta, 
    el("p", { class: "grande" }, redondo(t.bpm), el("span", { class: "unidad" }, " BPM")),
    insignia(t.confianza),
    t.sugerencia
      ? el("p", { class: "destacado" }, `Probablemente lo sientas a ${redondo(t.alternativas[t.sugerencia])} BPM.`)
      : null,
    el("p", {}, `Si lo contás al doble o a la mitad: ${redondo(t.alternativas.doble)} o ${redondo(t.alternativas.mitad)} BPM.`),
    el("p", {}, t.estable ? "Tempo estable." : `El tempo varía entre ${redondo(t.rango[0])} y ${redondo(t.rango[1])} BPM.`),
    t.regularidad < 0.7
      ? el("p", { class: "aviso" }, "El pulso es irregular (tempo libre o rubato): tomá el número como aproximado.")
      : null,
    t.aviso ? el("p", { class: "aviso" }, t.aviso) : null,
    el("p", { class: "tenue" }, textoSegundoMetodo(t.segundo_metodo)),
    curvaDeTempo(t.curva, estado.resultado.archivo.duracion)
  );
}

const SUBDIVISION = {
  binaria: "Cada pulso se divide en 2 (subdivisión binaria).",
  ternaria: "Cada pulso se divide en 3 (subdivisión ternaria).",
  "no clara": "No queda claro si cada pulso se divide en 2 o en 3.",
};

function dibujarCompas(c) {
  const tarjeta = $("t-compas");
  tarjeta.replaceChildren(el("h2", {}, "Compás"));
  if (!c.lectura) {
    anexar(tarjeta, el("p", { class: "grande" }, "—"), insignia("baja"), el("p", {}, c.motivo));
    return;
  }
  const segundo = c.segundo_metodo;
  let origen;
  if (c.fuente === "periodicidad") {
    origen = `Cuenta en ${c.pulsos_por_compas}: la armonía y el bajo se repiten cada ${c.pulsos_por_compas} pulsos (o múltiplos).`;
  } else {
    origen = `Cuenta en ${c.pulsos_por_compas}: así cuentan el ${porcentaje(c.acuerdo)} de los ${c.compases_contados} compases detectados.`;
  }
  anexar(
    tarjeta,
    el("p", { class: "grande" }, c.lectura),
    c.alternativa ? el("p", { class: "tenue" }, c.alternativa) : null,
    insignia(c.confianza),
    el("p", {}, origen),
    segundo && segundo.confirma
      ? el("p", { class: "tenue" }, "Un segundo método (cada cuántos pulsos se repite la armonía) confirma el compás.")
      : null,
    el("p", {}, SUBDIVISION[c.subdivision.tipo]),
    ...c.avisos.map((a) => el("p", { class: "aviso" }, a))
  );
}

function nombreTonalidad(t) {
  return t[estado.notacion];
}

function dibujarTonalidad(k, afinacion) {
  const otra = estado.notacion === "latino" ? "americano" : "latino";
  const tarjeta = $("t-tonalidad");
  tarjeta.replaceChildren();
  anexar(
    tarjeta,
    el("h2", {}, "Tonalidad"),
    el("p", { class: "grande" }, nombreTonalidad(k.principal)),
    el("p", { class: "tenue" }, `(${k.principal[otra]})`),
    insignia(k.confianza)
  );
  const alternativas = k.alternativas.map(
    (a) => `${nombreTonalidad(a)} (${a.motivo === "relativa" ? "su relativa" : "segunda opción del modelo"})`
  );
  anexar(tarjeta, el("p", {}, `También podría ser: ${alternativas.join(", ")}.`));

  const segundo = k.segundo_metodo;
  if (segundo) {
    const texto = {
      igual: "Los acordes detectados apuntan a la misma tonalidad.",
      relativa: `Los acordes detectados apuntan a ${nombreTonalidad(segundo)}, su relativa.`,
      distinta: `Los acordes detectados apuntan a ${nombreTonalidad(segundo)}: no coincide, así que hay dudas.`,
    }[segundo.acuerdo];
    anexar(tarjeta, el("p", { class: "tenue" }, texto));
  }
  for (const cambio of k.por_tramos.cambios) {
    anexar(tarjeta, 
      el("p", { class: "aviso" }, `Posible cambio de tonalidad: entre ${mmss(cambio.inicio)} y ${mmss(cambio.fin)} parece estar en ${nombreTonalidad(cambio)}.`)
    );
  }
  if (afinacion.aviso) anexar(tarjeta, el("p", { class: "aviso" }, afinacion.aviso));
}

function nombreAcorde(segmento) {
  if (!segmento) return "—";
  return segmento[estado.detalle === "simple" ? `${estado.notacion}_simple` : estado.notacion];
}

function nombresDelCompas(compas) {
  const nombres = [];
  for (const i of compas.acordes) {
    const nombre = nombreAcorde(estado.resultado.acordes.segmentos[i]);
    if (nombres[nombres.length - 1] !== nombre) nombres.push(nombre);
  }
  return nombres.length ? nombres.join(" · ") : "—";
}

function dibujarAcordes() {
  const acordes = estado.resultado.acordes;
  const resumen = estado.detalle === "simple" ? acordes.resumen_simple : acordes.resumen;
  $("nota-grilla").textContent = estado.resultado.compas.grilla_aproximada
    ? "Grilla aproximada: no se sabe con seguridad en qué pulso empieza cada compás. Hacé clic en un compás para escucharlo desde ahí."
    : "Hacé clic en un compás para escucharlo desde ahí.";
  $("nota-acordes").textContent =
    estado.detalle === "simple"
      ? "Modo simple: solo mayor y menor, que es lo más confiable. Pasá a “Completos” para ver séptimas, bajos e inversiones."
      : "Modo completo: incluye séptimas, bajos e inversiones, que fallan más seguido.";
  $("resumen-acordes").replaceChildren(
    ...resumen.map((a) => el("span", { class: "chip" }, a[estado.notacion], el("span", {}, porcentaje(a.proporcion))))
  );
  if (!resumen.length) $("resumen-acordes").append(el("p", { class: "tenue" }, "No se detectaron acordes."));

  const celdas = estado.resultado.compases.map((compas, i) =>
    el(
      "button",
      {
        type: "button",
        class: "celda",
        "data-i": String(i),
        title: `Escuchar desde ${mmss(compas.inicio)}`,
        onclick: () => {
          audio.currentTime = compas.inicio;
          audio.play().catch(() => {});
        },
      },
      el("span", { class: "num" }, compas.etiqueta),
      el("span", { class: "nombres" }, nombresDelCompas(compas))
    )
  );
  $("grilla").replaceChildren(...celdas);
  if (!celdas.length) $("grilla").append(el("p", { class: "tenue" }, "No se detectaron compases."));
}

// ---------------------------------------------------------------- notación

function marcarBotones() {
  for (const boton of document.querySelectorAll("[data-notacion]")) {
    boton.setAttribute("aria-pressed", String(boton.dataset.notacion === estado.notacion));
  }
  for (const boton of document.querySelectorAll("[data-detalle]")) {
    boton.setAttribute("aria-pressed", String(boton.dataset.detalle === estado.detalle));
  }
}

for (const boton of document.querySelectorAll("[data-notacion]")) {
  boton.addEventListener("click", () => {
    estado.notacion = boton.dataset.notacion;
    guardarPreferencia("notacion", estado.notacion);
    marcarBotones();
    if (estado.resultado) dibujarNombres();
  });
}
for (const boton of document.querySelectorAll("[data-detalle]")) {
  boton.addEventListener("click", () => {
    estado.detalle = boton.dataset.detalle;
    guardarPreferencia("detalle", estado.detalle);
    marcarBotones();
    if (estado.resultado) dibujarNombres();
  });
}

// ---------------------------------------------------------------- reproducción

function actualizarReproduccion() {
  if (!estado.resultado) return;
  const t = audio.currentTime;
  const segmentos = estado.resultado.acordes.segmentos;

  const i = buscar(segmentos, t);
  const actual = i >= 0 && t < segmentos[i].fin ? segmentos[i] : null;
  $("acorde-actual").textContent = nombreAcorde(actual);
  let siguiente = null;
  for (let j = i + 1; j < segmentos.length; j++) {
    if (segmentos[j].es_acorde && nombreAcorde(segmentos[j]) !== nombreAcorde(actual)) {
      siguiente = segmentos[j];
      break;
    }
  }
  $("acorde-siguiente").textContent = nombreAcorde(siguiente);

  const compases = estado.resultado.compases;
  const k = buscar(compases, t);
  const compas = k >= 0 && t < compases[k].fin ? compases[k] : null;
  $("compas-actual").textContent = compas ? compas.etiqueta : "—";
  if (k !== estado.compasActivo) {
    $("grilla").querySelector(".celda.activa")?.classList.remove("activa");
    const celda = $("grilla").querySelector(`.celda[data-i="${k}"]`);
    if (celda) {
      celda.classList.add("activa");
      if ($("seguir").checked && !audio.paused) desplazarGrilla(celda);
    }
    estado.compasActivo = k;
  }

  const p = buscar(estado.pulsos, t, null);
  const cerca = p >= 0 && t - estado.pulsos[p] < 0.25;
  const porCompas = estado.resultado.compas.pulsos_por_compas;
  let numero = cerca ? estado.numeros[p] : null;
  // Si falta un primer tiempo, la cuenta seguiría de largo (8, 9, 10…): mejor no mostrar nada
  if (numero && porCompas && numero > porCompas + 1) numero = null;
  const cuenta = $("cuenta");
  cuenta.textContent = numero ? String(numero) : "";
  cuenta.classList.toggle("uno", numero === 1);
}

/** Mueve solo la grilla (no la página) para que se vea el compás que está sonando. */
function desplazarGrilla(celda) {
  const grilla = $("grilla");
  const arriba = celda.offsetTop;
  const abajo = arriba + celda.offsetHeight;
  if (arriba < grilla.scrollTop || abajo > grilla.scrollTop + grilla.clientHeight) {
    grilla.scrollTo({ top: Math.max(0, arriba - grilla.clientHeight / 3), behavior: "smooth" });
  }
}

function asegurarContextoDeAudio() {
  const Contexto = window.AudioContext || window.webkitAudioContext;
  if (!contextoAudio && Contexto) contextoAudio = new Contexto();
  if (contextoAudio && contextoAudio.state === "suspended") contextoAudio.resume();
}

function sonarClic(cuando, acento) {
  const oscilador = contextoAudio.createOscillator();
  const volumen = contextoAudio.createGain();
  oscilador.frequency.value = acento ? 1760 : 1100;
  volumen.gain.setValueAtTime(0.0001, cuando);
  volumen.gain.exponentialRampToValueAtTime(acento ? 0.5 : 0.3, cuando + 0.002);
  volumen.gain.exponentialRampToValueAtTime(0.0001, cuando + 0.05);
  oscilador.connect(volumen).connect(contextoAudio.destination);
  oscilador.start(cuando);
  oscilador.stop(cuando + 0.06);
  clicsPendientes.add(oscilador);
  oscilador.addEventListener("ended", () => clicsPendientes.delete(oscilador));
}

/** Los clics se programan ~0,1 s antes: al pausar o saltar hay que cancelar los que faltan sonar. */
const clicsPendientes = new Set();

function cancelarClics() {
  for (const oscilador of clicsPendientes) {
    try {
      oscilador.stop();
    } catch {
      /* ya terminó */
    }
  }
  clicsPendientes.clear();
}

function reiniciarClics() {
  cancelarClics();
  estado.proximoClic = buscar(estado.pulsos, audio.currentTime - 0.001, null) + 1;
}

function programarClics() {
  if (!$("clic").checked || audio.paused || audio.seeking || !contextoAudio) return;
  const t = audio.currentTime;
  const pulsos = estado.pulsos;
  while (estado.proximoClic < pulsos.length && pulsos[estado.proximoClic] < t - 0.03) estado.proximoClic++;
  while (estado.proximoClic < pulsos.length && pulsos[estado.proximoClic] < t + 0.12) {
    const pulso = pulsos[estado.proximoClic];
    const cuando = contextoAudio.currentTime + Math.max(0, (pulso - t) / audio.playbackRate);
    sonarClic(cuando, estado.primeros.has(pulso.toFixed(3)));
    estado.proximoClic++;
  }
}

let temporizador = null;

audio.addEventListener("play", () => {
  if ($("clic").checked) asegurarContextoDeAudio();
  reiniciarClics();
  clearInterval(temporizador);
  temporizador = setInterval(() => {
    programarClics();
    actualizarReproduccion();
  }, 30);
});
audio.addEventListener("pause", () => {
  clearInterval(temporizador);
  cancelarClics();
  actualizarReproduccion();
});
audio.addEventListener("seeking", cancelarClics);
audio.addEventListener("seeked", () => {
  reiniciarClics();
  actualizarReproduccion();
});
audio.addEventListener("ratechange", reiniciarClics);
audio.addEventListener("error", () => {
  if (estado.resultado && audio.getAttribute("src")) $("audio-error").hidden = false;
});

$("clic").addEventListener("change", () => {
  if ($("clic").checked) asegurarContextoDeAudio();
  reiniciarClics();
});

function detenerReproduccion() {
  audio.pause();
  clearInterval(temporizador);
  cancelarClics();
  audio.removeAttribute("src");
  audio.load();
}

marcarBotones();
