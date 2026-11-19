// Pantalla pública (TV). Solo lectura: muestra el estado que manda el servidor.
// Nunca recibe las manos de los jugadores (el servidor solo envía cuántas cartas tienen).
import { Countdown, GameSocket, Sfx, clear, el, isLoopbackHost, joinUrl, qrSrc } from "./common.js";
import { cardEl, pigMeter, pigSvg } from "./cards.js";

const app = document.getElementById("app");
const statusDot = document.getElementById("status");
const timer = new Countdown();
const sfx = new Sfx();
const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
let state = null;
let connected = false;

const socket = new GameSocket({
  hello: () => ({ role: "tv" }),
  onStatus: (s) => {
    connected = s === "open";
    statusDot.className = `status-dot ${s}`;
    statusDot.setAttribute("aria-label", connected ? "Conectado" : "Reconectando");
    if (!connected && state) render();
  },
  onMessage: (msg) => {
    if (msg.type !== "state") return;
    const prev = state;
    state = msg;
    const w = msg.window;
    timer.set(w ? w.remaining_ms : null, w ? w.duration_ms : 0, msg.paused);
    render();
    react(prev, msg);
  },
});
socket.connect();
setInterval(tickBar, 200);

function nameOf(id) {
  return state?.players.find((p) => p.id === id)?.name ?? "?";
}

function tickBar() {
  const bar = document.getElementById("wbar");
  if (bar) bar.style.width = `${Math.round(timer.fraction() * 100)}%`;
}

// ------------------------------------------------------------------ efectos
function react(prev, next) {
  if (!prev) return;
  if (next.window && (!prev.window || prev.window.card.uid !== next.window.card.uid)) sfx.play();
  if (next.window && prev.window && next.window.chain.length > prev.window.chain.length) sfx.neigh();
  if (next.active && next.active !== prev.active && next.phase === "playing") {
    sfx.turn();
    document.querySelector(`.pen[data-id="${next.active}"]`)?.classList.add("flash");
  }
  const pigs = (s) => s.players.reduce((a, p) => a + p.pigs, 0);
  if (next.phase === "playing" && pigs(next) > pigs(prev)) sfx.oink();
  if (prev.phase !== "finished" && next.phase === "finished") {
    sfx.fanfare();
    confetti();
  }
}

function confetti() {
  if (reducedMotion) return;
  const box = el("div", { class: "confetti", "aria-hidden": "true" });
  const bits = ["🐷", "🐽", "🌸", "⭐", "🎉"];
  for (let i = 0; i < 40; i++) {
    box.append(el("span", {
      text: bits[i % bits.length],
      style: { left: `${Math.random() * 100}vw`, animationDuration: `${2.5 + Math.random() * 2.5}s`, animationDelay: `${Math.random() * 1.5}s` },
    }));
  }
  document.body.append(box);
  setTimeout(() => box.remove(), 7000);
}

// ------------------------------------------------------------------ render
function render() {
  clear(app);
  if (!state) {
    app.append(el("p", { text: "Conectando…" }));
    return;
  }
  if (state.phase === "lobby") renderLobby();
  else if (state.phase === "playing") renderTable();
  else renderFinal();
  if (state.paused) {
    app.append(el("div", { class: "overlay" }, el("h2", { text: "Pausa" }), el("p", { text: "El anfitrión ha parado la partida un momento." })));
  }
  if (!connected) {
    app.append(el("div", { class: "overlay" }, el("h2", { text: "Reconectando…" }), el("p", { text: "Comprueba que la TV sigue en la red de casa." })));
  }
}

function joinBase() {
  return state.join_base || location.origin;
}

function renderLobby() {
  const base = joinBase();
  const url = joinUrl(base, state.code);
  const host = new URL(base).hostname;
  const players = state.players;
  const card = el("div", { class: "join-card" },
    el("img", { src: qrSrc(url), alt: "Código QR para unirse", width: "340", height: "340" }),
    el("div", { class: "room" }, "Código de la pocilga", el("b", { text: state.code })),
    el("div", { class: "url", text: url }));
  if (isLoopbackHost(host)) {
    card.append(el("p", { class: "warn", text: "Esta TV usa «localhost»: los móviles no podrán entrar. Abre esta pantalla con la IP de Home Assistant." }));
  }
  const seats = el("div", { class: "seats" });
  for (const p of players) {
    seats.append(el("div", { class: `seat-chip${p.connected ? "" : " off"}` }, el("span", { class: "ava", text: p.avatar }), p.name));
  }
  for (let i = players.length; i < state.min_players; i++) {
    seats.append(el("div", { class: "seat-chip ghost" }, el("span", { class: "ava", text: "🐽" }), "Falta alguien"));
  }
  const sound = el("button", { class: "btn", style: { marginTop: "3vh", fontSize: "2vh", minHeight: "5vh" }, onclick: (ev) => {
    if (sfx.enable()) ev.currentTarget.textContent = "🔊 Sonido activado";
  }, text: sfx.enabled ? "🔊 Sonido activado" : "🔈 Activar sonido" });
  const goal = state.settings.goal || (players.length >= 5 ? 5 : 6);
  app.append(el("section", { class: "lobby" },
    el("div", {},
      el("div", { class: "hero" }, pigSvg("rosado"), pigSvg("jabali"), pigSvg("coqueta")),
      el("h1", {}, "Cerditos", el("b", { text: "Locos" })),
      el("ul", { class: "how" },
        el("li", { text: `Junta ${goal} cerdos en tu pocilga para ganar.` }),
        el("li", { text: "En tu turno: roba, y juega una carta o roba otra." }),
        el("li", { text: "Fastidia a los demás… y frena sus jugadas con «¡Ni hablar!»." })),
      seats,
      el("p", { style: { fontSize: "2.2vh", opacity: 0.8 }, text: `${players.length} de ${state.max_players} jugadores · el anfitrión empieza desde Home Assistant.` }),
      sound),
    card));
}

function topBar() {
  const active = state.players.find((p) => p.id === state.active);
  return el("header", { class: "tv-top" },
    el("span", { class: "brand" }, "Cerditos ", el("b", { text: "Locos" })),
    active && state.phase === "playing" ? el("span", { class: "turn" }, el("span", { class: "ava", text: active.avatar }), `Turno de ${active.name}`) : null,
    el("span", { class: "goal", text: `Meta: ${state.goal} 🐷` }),
    el("span", { class: "pile" }, el("b", { text: String(state.deck_count) }), el("span", { text: "en el mazo" })),
    el("span", { class: "pile" }, el("b", { text: String(state.discard_count) }), el("span", { text: "en el monte" })),
    el("span", { class: "pile" }, el("b", { text: String(state.nursery_count) }), el("span", { text: "lechones" })));
}

function renderTable() {
  const waiting = new Set(state.waiting_for.map((d) => d.seat));
  const pens = el("section", { class: `pens n${state.players.length}` });
  for (const p of state.players) {
    let tag = null;
    if (!p.connected) tag = el("span", { class: "tag off", text: "desconectado" });
    else if (waiting.has(p.id) && p.id !== state.active) tag = el("span", { class: "tag", text: "pensando…" });
    else if (p.id === state.active) tag = el("span", { class: "tag", text: "le toca" });
    const cards = el("div", { class: "cards" });
    const sorted = [...p.pen].sort((a, b) => order(a) - order(b));
    for (const c of sorted) cards.append(cardEl(c, { size: "mini" }));
    if (!p.pen.length) cards.append(el("span", { class: "empty", text: "Pocilga vacía" }));
    pens.append(el("article", { class: `pen${p.id === state.active ? " active" : ""}${p.connected ? "" : " off"}`, "data-id": p.id },
      el("header", {},
        el("span", { class: "ava", text: p.avatar }),
        el("span", { class: "who" },
          el("span", { class: "nm", text: p.name }),
          el("span", { class: "line" }, el("span", { class: "handcount", title: "Cartas en la mano", text: `🂠 ${p.hand_count}` }), tag),
          pigMeter(p.pigs, state.goal)),
        el("span", { class: "count", text: String(p.pigs) })),
      cards));
  }
  app.append(topBar(), el("div", { class: "tv-main" }, pens, el("aside", { class: "side" }, nowPanel(), logPanel())));
  tickBar();
}

function order(card) {
  return { baby: 0, pig: 1, magic_pig: 2, perk: 3, pest: 4 }[card.kind] ?? 5;
}

function nowPanel() {
  const w = state.window;
  if (w) {
    const panel = el("section", { class: "now" },
      el("h2", { text: w.chain.length ? "¡Réplica!" : "¿Alguien replica?" }),
      el("p", { class: "lead" }, el("b", { text: nameOf(w.actor) }), " juega"),
      cardEl(w.card));
    if (w.chain.length) {
      panel.append(el("div", { class: "chain" }, w.chain.map((c) => cardEl(c, { size: "mini" }))),
        el("span", { class: `verdict ${w.cancels ? "no" : "yes"}`, text: w.cancels ? "Ahora mismo: ANULADA" : "Ahora mismo: VALE" }));
    }
    panel.append(el("div", { class: "bar" }, el("span", { id: "wbar" })));
    if (w.waiting.length) {
      panel.append(el("p", { class: "sub", text: "Esperando a:" }), el("div", { class: "waiting" }, w.waiting.map((id) => el("span", { text: nameOf(id) }))));
    }
    return panel;
  }
  const d = state.waiting_for.find((x) => x.kind !== "turn") || state.waiting_for[0];
  const panel = el("section", { class: "now" });
  if (state.in_play.length) {
    panel.append(el("h2", { text: "En juego" }), cardEl(state.in_play[state.in_play.length - 1]));
  }
  if (d) {
    const who = state.players.find((p) => p.id === d.seat);
    if (d.kind === "turn") {
      panel.append(el("h2", { text: `Le toca a ${who?.name ?? "?"}` }), el("p", { class: "lead", text: "Juega una carta o roba otra." }));
    } else {
      panel.append(el("h2", { text: `Esperando a ${who?.name ?? "?"}` }));
      if (d.source && !state.in_play.length) panel.append(cardEl(d.source));
      panel.append(el("p", { class: "lead", text: d.prompt }));
    }
    if (who && !who.connected && d.remaining_ms !== null) {
      panel.append(el("p", { class: "sub", text: `Sin conexión: se jugará por defecto en ${Math.ceil(d.remaining_ms / 1000)} s.` }));
    }
  } else if (!state.in_play.length && state.discard_top.length) {
    panel.append(el("h2", { text: "Última al monte" }), cardEl(state.discard_top[state.discard_top.length - 1]));
  }
  return panel;
}

function logPanel() {
  const list = el("ol");
  for (const e of [...state.log].reverse().slice(0, 9)) list.append(el("li", { text: e.text }));
  return el("section", { class: "log" }, el("h3", { text: "Qué ha pasado" }), list);
}

function renderFinal() {
  const winners = state.players.filter((p) => state.winners.includes(p.id));
  const why = {
    goal: `Llegó a ${state.goal} cerdos.`,
    deck: "Se acabó el mazo: gana quien tenía más cerdos.",
    host: "El anfitrión terminó la partida: gana quien tenía más cerdos.",
    players: "Se quedó solo en la mesa.",
  }[state.end_reason] || "";
  const table = el("table");
  for (const p of [...state.players].sort((a, b) => b.pigs - a.pigs)) {
    table.append(el("tr", {}, el("td", { text: p.avatar }), el("td", { text: p.name }), el("td", { class: "n", text: `${p.pigs} 🐷` })));
  }
  app.append(topBar(), el("section", { class: "final" },
    el("h1", { text: winners.length > 1 ? "¡Empate en la pocilga!" : "¡Tenemos ganador!" }),
    el("div", { class: "winners" }, winners.map((p) => el("div", { class: "winner" }, el("span", { class: "ava", text: p.avatar }), p.name))),
    el("p", { class: "why", text: why }),
    table));
}
