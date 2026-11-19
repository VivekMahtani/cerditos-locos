// Mando del jugador en el móvil: su mano, sus decisiones y sus réplicas.
// El servidor decide qué es legal; aquí solo se muestran las opciones que envía.
import { Countdown, GameSocket, clear, el } from "./common.js";
import { KIND_LABEL, PIG_KINDS, cardEl, pigMeter, pigSvg } from "./cards.js";

const AVATARS = ["🐷", "🐮", "🐔", "🐑", "🐴", "🦆", "🐐", "🐰", "🐶", "🐱", "🦊", "🐸", "🦉", "🐝", "🦔", "🐢"];
const STORE = "cerditos_locos_session";
const app = document.getElementById("app");
const statusDot = document.getElementById("status");
const timer = new Countdown();
const params = new URLSearchParams(location.search);

let state = null;
let mode = "boot"; // boot | join | in
let pendingJoin = null;
let joinError = "";
let notice = "";
let busy = false; // acción enviada, esperando respuesta
let sheet = null; // { uid, target }
let picked = { id: null, values: [] }; // selección en la decisión abierta
let form = { code: (params.get("code") || "").toUpperCase().slice(0, 4), name: "", avatar: null };
try {
  form.name = localStorage.getItem("cerditos_locos_name") || "";
} catch (err) { /* modo privado */ }

function storedSession() {
  try { return localStorage.getItem(STORE); } catch (err) { return null; }
}
function storeSession(v) {
  try { v ? localStorage.setItem(STORE, v) : localStorage.removeItem(STORE); } catch (err) { /* ignorado */ }
}

const socket = new GameSocket({
  hello: () => {
    const session = storedSession();
    if (session) return { role: "player", session };
    if (pendingJoin) return { role: "player", ...pendingJoin };
    return null;
  },
  onStatus: (s) => {
    statusDot.className = `status-dot ${s}`;
    statusDot.setAttribute("aria-label", s === "open" ? "Conectado" : "Reconectando");
    if (s === "open" && !storedSession() && !pendingJoin && mode === "boot") {
      mode = "join";
      render();
    }
    if (s !== "open") busy = false;
    if (s !== "open" && mode === "in") render();
  },
  onMessage: handle,
});
socket.connect();
setInterval(tickTimer, 200);

// Mantener la pantalla encendida cuando el navegador lo permite (requiere HTTPS).
let wakeLock = null;
async function keepAwake() {
  try {
    if (!wakeLock && navigator.wakeLock && document.visibilityState === "visible") {
      wakeLock = await navigator.wakeLock.request("screen");
      wakeLock.addEventListener("release", () => { wakeLock = null; });
    }
  } catch (err) { /* no disponible */ }
}
document.addEventListener("click", keepAwake, { passive: true });
document.addEventListener("visibilitychange", keepAwake);

/** Vibra solo si el jugador ya ha tocado la página (los navegadores lo exigen). */
function buzz(pattern) {
  if (navigator.userActivation && !navigator.userActivation.hasBeenActive) return;
  navigator.vibrate?.(pattern);
}

function handle(msg) {
  switch (msg.type) {
    case "welcome":
      if (msg.session) storeSession(msg.session);
      pendingJoin = null;
      joinError = "";
      mode = "in";
      break;
    case "state": {
      if (mode === "in" && !msg.you) return; // aún sin vincular
      const prevTurn = state?.you?.can_draw_instead;
      state = msg;
      busy = false;
      const r = msg.you?.react;
      const w = msg.window;
      timer.set(w && r ? w.remaining_ms : null, w ? w.duration_ms : 0, msg.paused);
      tidy();
      if (!prevTurn && msg.you?.can_draw_instead) buzz([60, 40, 60]);
      break;
    }
    case "ack":
      busy = false;
      if (msg.ref === "play") buzz(30);
      return;
    case "error":
      return handleError(msg);
    case "kicked":
    case "removed":
    case "left":
      storeSession(null);
      mode = "join";
      notice = msg.message || "";
      state = null;
      break;
    case "replaced":
      storeSession(null);
      mode = "join";
      notice = msg.message;
      socket.stop();
      break;
    default:
      return;
  }
  render();
}

function handleError(msg) {
  busy = false;
  if (msg.ref === "hello" || ["session_expired", "bad_code", "name_taken", "room_full", "too_many_attempts", "game_running"].includes(msg.code)) {
    if (msg.code === "session_expired") storeSession(null);
    pendingJoin = null;
    mode = "join";
    joinError = msg.message;
  } else {
    notice = msg.message;
  }
  render();
}

/** Cierra hojas y selecciones que ya no tienen sentido con el estado nuevo. */
function tidy() {
  const you = state?.you;
  if (!you) return;
  if (sheet && !you.hand.some((c) => c.uid === sheet.uid)) sheet = null;
  const open = you.decisions.find((d) => d.kind !== "turn");
  if (!open || open.id !== picked.id) picked = { id: open?.id ?? null, values: [] };
}

function send(type, extra = {}) {
  if (busy) return;
  if (!socket.send({ type, ...extra })) {
    notice = "Sin conexión. Reintentando…";
    render();
    return;
  }
  busy = true;
  notice = "";
  render();
}

function tickTimer() {
  const bar = document.getElementById("rbar");
  if (bar) bar.style.width = `${Math.round(timer.fraction() * 100)}%`;
}

function playerById(id) {
  return state?.players.find((p) => p.id === id);
}

// ------------------------------------------------------------------ render
function render() {
  clear(app);
  if (mode === "boot") {
    app.append(el("p", { class: "center", text: "Conectando…" }));
    return;
  }
  if (mode === "join" || !state) {
    renderJoin();
    return;
  }
  app.append(topBar());
  if (notice) app.append(el("div", { class: "notice", role: "alert", text: notice }));
  if (state.phase === "lobby") renderLobby();
  else if (state.phase === "finished") renderFinished();
  else renderGame();
  if (sheet) renderSheet();
  tickTimer();
}

function topBar() {
  const you = state?.you;
  const me = playerById(you?.id);
  return el("header", { class: "play-top" },
    el("span", { class: "brand" }, "Cerditos ", el("b", { text: "Locos" })),
    you ? el("span", { class: "me" }, el("span", { class: "ava", text: you.avatar }),
      state.phase === "lobby" ? you.name : pigMeter(me?.pigs ?? 0, state.goal)) : null);
}

function renderJoin() {
  const err = joinError || notice;
  notice = "";
  const avatars = el("div", { class: "avatars", role: "group", "aria-label": "Elige avatar" },
    AVATARS.map((a) => el("button", {
      type: "button", text: a, "aria-pressed": String(form.avatar === a), "aria-label": `Avatar ${a}`,
      onclick: (ev) => {
        form.avatar = a;
        ev.currentTarget.parentElement.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === a)));
      },
    })));
  const code = el("input", { class: "code", id: "code", value: form.code, maxlength: "4", autocomplete: "off", autocapitalize: "characters", required: true, "aria-label": "Código de la pocilga" });
  const name = el("input", { id: "name", value: form.name, maxlength: "16", autocomplete: "nickname", enterkeyhint: "go", required: true, "aria-label": "Tu nombre" });
  code.addEventListener("input", () => { code.value = code.value.toUpperCase().replace(/[^A-Z]/g, ""); form.code = code.value; });
  name.addEventListener("input", () => { form.name = name.value; });
  const submit = el("button", { class: "btn primary block", type: "submit", text: "Entrar en la pocilga" });
  const f = el("form", { class: "panel enter", novalidate: true, onsubmit: (ev) => {
    ev.preventDefault();
    const n = name.value.trim();
    if (code.value.length !== 4) { joinError = "El código tiene 4 letras. Lo ves en la tele."; return render(); }
    if (!n) { joinError = "Escribe tu nombre."; return render(); }
    try { localStorage.setItem("cerditos_locos_name", n); } catch (e) { /* ignorado */ }
    pendingJoin = { code: code.value, name: n, avatar: form.avatar || undefined };
    joinError = "";
    submit.disabled = true;
    submit.textContent = "Entrando…";
    if (socket.open) socket.identify();
    else socket.reconnect();
  } },
  el("div", { class: "hero" }, pigSvg("coqueta")),
  el("h1", {}, "Cerditos ", el("b", { text: "Locos" })),
  err ? el("div", { class: "error", role: "alert", text: err }) : null,
  el("label", {}, "Código de la pocilga", code),
  el("label", {}, "Tu nombre", name),
  el("div", {}, el("p", { class: "sub", text: "Tu avatar (opcional)" }), avatars),
  submit);
  app.append(f);
}

function renderLobby() {
  const list = el("div", { class: "rivals", style: { flexWrap: "wrap" } },
    state.players.map((p) => el("span", { class: `rival${p.connected ? "" : " off"}` }, el("span", { class: "ava", text: p.avatar }), p.name)));
  app.append(el("section", { class: "panel center" },
    el("div", { class: "big-emoji", text: state.you.avatar }),
    el("h2", { text: "¡Ya estás en la pocilga!" }),
    el("p", { text: "Mira la tele. Cuando estéis todos, el anfitrión empezará la partida." }),
    el("p", { class: "sub", text: `Gana quien junte ${state.goal} cerdos.` })),
  el("div", { class: "section-title" }, el("h3", { text: "Jugadores" }), el("span", { text: `${state.players.length} de ${state.max_players}` })),
  list,
  el("div", { class: "btn-row" }, el("button", { class: "btn", onclick: () => {
    if (confirm("¿Salir de la pocilga?")) send("leave");
  }, text: "Salir" })));
}

function renderFinished() {
  const won = state.winners.includes(state.you.id);
  const names = state.winners.map((id) => playerById(id)?.name).filter(Boolean).join(" y ");
  app.append(el("section", { class: `panel center ${won ? "hot" : ""}` },
    el("div", { class: "big-emoji", text: won ? "🏆" : "🐽" }),
    el("h2", { text: won ? (state.winners.length > 1 ? "¡Empate, compartes la victoria!" : "¡Has ganado!") : `Gana ${names}` }),
    el("p", { text: `Tenías ${playerById(state.you.id)?.pigs ?? 0} cerdos.` }),
    el("p", { class: "sub", text: "El anfitrión puede preparar otra partida desde Home Assistant." })));
  renderPen();
}

function renderGame() {
  const you = state.you;
  const decision = you.decisions.find((d) => d.kind !== "turn");
  if (state.paused) {
    app.append(el("section", { class: "panel center" }, el("h2", { text: "Pausa" }), el("p", { text: "El anfitrión ha parado la partida un momento." })));
  } else if (you.react && !you.react.passed) {
    renderReact(you.react);
  } else if (decision) {
    renderDecision(decision);
  } else if (you.can_draw_instead) {
    app.append(el("section", { class: "panel hot" },
      el("h2", { text: "¡Te toca!" }),
      el("p", { text: "Toca una carta brillante para jugarla, o roba otra carta." }),
      el("div", { class: "btn-row" }, el("button", { class: "btn sun", disabled: busy, onclick: () => send("draw_instead"), text: "Robar en lugar de jugar" }))));
  } else {
    renderWaiting();
  }
  renderHand(!decision || decision.kind !== "discard");
  renderPen();
  renderRivals();
}

function renderWaiting() {
  const active = playerById(state.active);
  const panel = el("section", { class: "panel" }, el("h2", { text: `Turno de ${active?.name ?? "…"}` }));
  const w = state.window;
  if (w) {
    panel.append(el("p", {}, el("b", { text: playerById(w.actor)?.name ?? "?" }), ` juega ${w.card.name}.`));
    panel.append(el("p", { class: "sub", text: w.chain.length ? "Hay réplicas en juego…" : "Esperando por si alguien replica…" }));
  } else {
    const d = state.waiting_for[0];
    if (d && d.kind !== "turn") panel.append(el("p", { class: "sub", text: `${playerById(d.seat)?.name ?? "?"} está decidiendo: ${d.prompt}` }));
    else panel.append(el("p", { class: "sub", text: "Mira la tele para ver qué pasa." }));
  }
  app.append(panel);
}

function renderReact(r) {
  const w = state.window;
  const panel = el("section", { class: "panel hot" },
    el("h2", { text: w.chain.length ? "¡Han replicado!" : "¿Replicas?" }),
    el("p", {}, el("b", { text: playerById(w.last)?.name ?? "?" }),
      w.chain.length ? ` ha jugado ${w.chain[w.chain.length - 1].name} contra ` : " juega ",
      el("b", { text: w.card.name }), w.chain.length ? ` de ${playerById(w.actor)?.name ?? "?"}.` : "."),
    el("div", { class: "react-card" }, cardEl(w.card)),
    el("div", { class: "timer" }, el("span", { id: "rbar" })));
  if (w.chain.length) {
    panel.append(el("p", { class: "sub", text: w.cancels ? "Ahora mismo la carta queda ANULADA. Si replicas, vuelve a valer." : "Ahora mismo la carta VALE. Si replicas, queda anulada." }));
  }
  const row = el("div", { class: "btn-row" });
  const neighs = state.you.hand.filter((c) => r.cards.includes(c.uid));
  if (r.blocked) panel.append(el("p", { class: "sub", text: "🦟 Las moscas no te dejan replicar." }));
  else if (!neighs.length) panel.append(el("p", { class: "sub", text: "No tienes cartas de réplica." }));
  const seen = new Set();
  for (const c of neighs) {
    if (seen.has(c.name)) continue; // una por tipo basta
    seen.add(c.name);
    row.append(el("button", { class: "btn warn", disabled: busy, onclick: () => send("react", { window: r.window_id, card: c.uid }), text: `✋ ${c.name}` }));
  }
  row.append(el("button", { class: "btn", disabled: busy, onclick: () => send("react", { window: r.window_id, card: null }), text: "Dejar pasar" }));
  panel.append(row);
  app.append(panel);
}

function renderDecision(d) {
  const panel = el("section", { class: "panel hot" }, el("h2", { text: d.source ? d.source.name : "Decide" }), el("p", { text: d.prompt }));
  if (d.kind === "yes_no") {
    panel.append(el("div", { class: "btn-row" },
      el("button", { class: "btn ok", disabled: busy, onclick: () => send("decide", { decision: d.id, choice: true }), text: "Sí" }),
      el("button", { class: "btn", disabled: busy, onclick: () => send("decide", { decision: d.id, choice: false }), text: "No" })));
  } else if (d.kind === "player") {
    const box = el("div", { class: "choices" });
    for (const o of d.options) {
      const p = playerById(o.id);
      const on = picked.values[0] === o.id;
      box.append(el("button", { class: "choice-player", style: on ? { boxShadow: "0 0 0 3px var(--grass)" } : {}, "aria-pressed": String(on), onclick: () => { picked.values = [o.id]; render(); } },
        el("span", { class: "ava", text: o.avatar }), o.name, el("small", { text: p ? `${p.hand_count} cartas · ${p.pigs} 🐷` : "" })));
    }
    panel.append(box, el("div", { class: "btn-row" },
      el("button", { class: "btn primary", disabled: busy || !picked.values.length, onclick: () => send("decide", { decision: d.id, choice: picked.values[0] }), text: "Confirmar" })));
  } else {
    const grid = el("div", { class: "hand" });
    for (const c of d.options) {
      const on = picked.values.includes(c.uid);
      const node = cardEl(c, { state: on ? "selected" : "playable", onclick: () => {
        if (on) picked.values = picked.values.filter((u) => u !== c.uid);
        else if (d.max === 1) picked.values = [c.uid];
        else if (picked.values.length < d.max) picked.values = [...picked.values, c.uid];
        render();
      } });
      if (c.owner) node.append(el("span", { class: "owner", text: c.owner === state.you.id ? "tuyo" : `de ${c.owner_name}` }));
      grid.append(node);
    }
    const n = picked.values.length;
    const ok = n >= d.min && n <= d.max;
    const label = d.kind === "discard" ? `Descartar (${n}/${d.max})` : d.max > 1 ? `Confirmar (${n}/${d.max})` : "Confirmar";
    panel.append(grid, el("div", { class: "btn-row" },
      el("button", { class: `btn ${d.kind === "discard" ? "warn" : "primary"}`, disabled: busy || !ok, onclick: () => send("decide", { decision: d.id, choice: picked.values }), text: label })));
  }
  if (d.remaining_ms !== null) panel.append(el("p", { class: "sub", text: "Responde pronto o se elegirá por ti." }));
  app.append(panel);
}

function renderHand(interactive) {
  const you = state.you;
  const playable = you.playable || {};
  const myTurn = you.can_draw_instead;
  const grid = el("div", { class: "hand" });
  for (const c of you.hand) {
    const can = c.uid in playable;
    const st = myTurn ? (can ? "playable" : "dim") : null;
    grid.append(cardEl(c, { state: st, onclick: interactive ? () => { sheet = { uid: c.uid, target: null }; render(); } : null }));
  }
  if (!you.hand.length) grid.append(el("p", { class: "sub", text: "No tienes cartas." }));
  const me = playerById(you.id);
  app.append(el("div", { class: "section-title" }, el("h3", { text: "Tu mano" }), el("span", { text: `${you.hand.length} cartas · límite ${me?.hand_limit ?? 7}` })), grid);
}

function renderPen() {
  const me = playerById(state.you.id);
  if (!me) return;
  const pen = el("div", { class: "my-pen" }, me.pen.map((c) => cardEl(c, { size: "mini" })));
  if (!me.pen.length) pen.append(el("p", { class: "sub", text: "Tu pocilga está vacía." }));
  app.append(el("div", { class: "section-title" }, el("h3", { text: "Tu pocilga" }), el("span", { text: `${me.pigs} de ${state.goal} cerdos` })), pen);
}

function renderRivals() {
  const rivals = state.players.filter((p) => p.id !== state.you.id);
  app.append(el("div", { class: "section-title" }, el("h3", { text: "Rivales" })),
    el("div", { class: "rivals" }, rivals.map((p) => el("span", { class: `rival${p.id === state.active ? " active" : ""}${p.connected ? "" : " off"}` },
      el("span", { class: "ava", text: p.avatar }), el("span", {}, p.name, el("br"), el("b", { text: `${p.pigs} 🐷` }), ` · ${p.hand_count} cartas`)))));
}

function whyNot(card) {
  const you = state.you;
  if (card.kind === "neigh" || card.kind === "super_neigh") return "Las réplicas se juegan cuando otro jugador juega una carta.";
  if (!you.can_draw_instead) return "Solo puedes jugar cartas en tu turno.";
  if (card.kind === "trick") return "Algo en tu pocilga no te deja jugar trastadas ahora.";
  return "Ahora no puedes jugar esta carta.";
}

function renderSheet() {
  const you = state.you;
  const card = you.hand.find((c) => c.uid === sheet.uid);
  if (!card) return;
  const targets = you.playable?.[card.uid];
  const can = card.uid in (you.playable || {});
  const close = () => { sheet = null; render(); };
  const box = el("div", { class: "sheet", role: "dialog", "aria-label": card.name }, cardEl(card));
  if (!can) {
    box.append(el("p", { class: "why", text: whyNot(card) }), el("div", { class: "btn-row" }, el("button", { class: "btn block", onclick: close, text: "Cerrar" })));
  } else {
    if (targets) {
      box.append(el("h3", { text: "¿A quién se lo pones?" }));
      const list = el("div", { class: "choices", style: { width: "100%" } });
      for (const id of targets) {
        const p = playerById(id);
        const on = sheet.target === id;
        list.append(el("button", { class: "choice-player", style: on ? { boxShadow: "0 0 0 3px var(--grass)" } : {}, "aria-pressed": String(on), onclick: () => { sheet.target = id; render(); } },
          el("span", { class: "ava", text: p?.avatar ?? "?" }), p?.name ?? "?", el("small", { text: p ? `${p.pigs} 🐷` : "" })));
      }
      box.append(list);
    }
    const ready = !targets || sheet.target;
    let label = PIG_KINDS.has(card.kind) ? "Meter en mi pocilga" : card.kind === "perk" ? "Poner en mi pocilga" : "Jugar esta carta";
    if (targets && sheet.target) label = `Ponérselo a ${playerById(sheet.target)?.name ?? "?"}`;
    box.append(el("p", { class: "why", text: `${KIND_LABEL[card.kind]}. Al jugarla, los demás podrán replicar.` }),
      el("div", { class: "btn-row" },
        el("button", { class: "btn", onclick: close, text: "Cancelar" }),
        el("button", { class: "btn primary", disabled: busy || !ready, onclick: () => {
          const target = sheet.target;
          sheet = null;
          send("play", { card: card.uid, target: target ?? null });
        }, text: label })));
  }
  app.append(el("div", { class: "sheet-bg", onclick: (ev) => { if (ev.target === ev.currentTarget) close(); } }, box));
}
