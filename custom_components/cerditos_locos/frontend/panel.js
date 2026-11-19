// Panel de anfitrión dentro de Home Assistant (custom element, solo administradores).
// Obtiene el token de anfitrión con el WebSocket autenticado de HA y controla la partida.
// Origen: patrón del panel de Quiz del Salón (MIT), con controles propios del juego de cartas.
import { GameSocket, TV_PATH, clear, el, isLoopbackHost, joinUrl, qrSrc } from "./common.js";

const CSS_URL = new URL("./panel.css", import.meta.url).href;
const FONT_BASE = new URL("./fonts/", import.meta.url).href;

// @font-face no funciona dentro del shadow DOM: se declara una vez en el documento.
if (!document.getElementById("cerditos-locos-fonts")) {
  const style = document.createElement("style");
  style.id = "cerditos-locos-fonts";
  style.textContent = `@font-face{font-family:"Bungee";src:url("${FONT_BASE}bungee-latin.woff") format("woff");font-display:swap}`;
  document.head.append(style);
}
const PHASES = { lobby: "Sala de espera", playing: "Partida en curso", finished: "Partida terminada" };

class CerditosLocosPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = null;
    this._info = null;
    this._socket = null;
    this._status = "connecting";
    this._message = "";
    this._root = el("div", { class: "wrap" });
    this.shadowRoot.append(el("link", { rel: "stylesheet", href: CSS_URL }), this._root);
  }

  set hass(hass) {
    this._hass = hass;
    if (this._menu) this._menu.hass = hass;
    if (!this._started) {
      this._started = true;
      this._start();
    }
  }
  set narrow(v) {
    this._narrow = v;
    if (this._menu) this._menu.narrow = v;
  }
  set panel(p) {
    this._panel = p;
  }

  disconnectedCallback() {
    this._socket?.stop();
    this._started = false;
  }

  connectedCallback() {
    if (this._hass && !this._started) {
      this._started = true;
      this._start();
    }
  }

  async _fetchToken() {
    this._info = await this._hass.callWS({ type: "cerditos_locos/host_token" });
  }

  async _start() {
    this._render();
    try {
      await this._fetchToken();
    } catch (err) {
      this._message = "No se pudo obtener el acceso de anfitrión. ¿Está cargada la integración y eres administrador?";
      this._render();
      return;
    }
    this._socket = new GameSocket({
      hello: () => ({ role: "host", token: this._info.token }),
      onStatus: (s) => { this._status = s; this._renderStatus(); },
      onMessage: (m) => this._onMessage(m),
    });
    this._socket.connect();
  }

  async _onMessage(msg) {
    if (msg.type === "state") {
      this._state = msg;
      const active = this.shadowRoot.activeElement;
      if (active && active.tagName === "SELECT") {
        if (!this._deferred) {
          this._deferred = true;
          active.addEventListener("blur", () => { this._deferred = false; this._render(); }, { once: true });
        }
        return;
      }
      this._render();
    } else if (msg.type === "error") {
      if (msg.code === "bad_token") {
        try {
          await this._fetchToken();
          this._socket.reconnect();
        } catch (err) { /* se informa abajo */ }
      }
      this._message = msg.message;
      this._renderStatus();
    } else if (msg.type === "ack") {
      this._message = "";
      this._renderStatus();
    }
  }

  _send(type, extra = {}) {
    if (!this._socket?.send({ type, ...extra })) {
      this._message = "Sin conexión con el juego. Reintentando…";
      this._renderStatus();
    }
  }

  _base() {
    return this._state?.join_base || this._info?.join_base || location.origin;
  }

  _name(id) {
    return this._state?.players.find((p) => p.id === id)?.name ?? "?";
  }

  // ------------------------------------------------------------------ render
  _render() {
    const root = clear(this._root);
    const head = el("header", { class: "head" });
    const Menu = customElements.get("ha-menu-button");
    if (Menu && this._narrow) {
      this._menu = document.createElement("ha-menu-button");
      this._menu.hass = this._hass;
      this._menu.narrow = this._narrow;
      head.append(this._menu);
    }
    head.append(el("h1", {}, "Cerditos ", el("span", { text: "Locos" })), el("span", { id: "status", class: "status" }));
    root.append(head);
    this._statusLine = el("div", { class: "msg", role: "status" });
    root.append(this._statusLine);
    const s = this._state;
    if (!s) {
      root.append(el("div", { class: "card", text: this._message || "Conectando con el juego…" }));
      this._renderStatus();
      return;
    }
    const grid = el("div", { class: "grid" });
    grid.append(this._controlsCard(s), this._screensCard(s), this._playersCard(s));
    grid.append(s.phase === "lobby" ? this._configCard(s) : this._liveCard(s));
    root.append(grid);
    this._renderStatus();
  }

  _renderStatus() {
    const badge = this.shadowRoot.getElementById("status");
    if (badge) {
      badge.className = `status ${this._status}`;
      badge.textContent = this._status === "open" ? "Conectado" : "Reconectando…";
    }
    if (this._statusLine) {
      this._statusLine.textContent = this._message || "";
      this._statusLine.hidden = !this._message;
    }
  }

  _controlsCard(s) {
    const connected = s.players.filter((p) => p.connected).length;
    const card = el("section", { class: "card controls" }, el("h2", { text: PHASES[s.phase] + (s.paused ? " (en pausa)" : "") }));
    const row = el("div", { class: "buttons" });
    if (s.phase === "lobby") {
      const can = connected >= s.min_players;
      row.append(el("button", { class: "primary", disabled: !can, onclick: () => this._send("start"), text: "Empezar partida" }));
      if (!can) card.append(el("p", { class: "sub", text: `Se necesitan al menos ${s.min_players} jugadores conectados (máximo ${s.max_players}).` }));
    } else if (s.phase === "finished") {
      row.append(el("button", { class: "primary", onclick: () => this._send("new_game", { keep_players: true }), text: "Nueva partida con los mismos jugadores" }));
      row.append(el("button", { onclick: () => this._send("new_game", { keep_players: false }), text: "Nueva partida vacía" }));
    } else {
      row.append(s.paused
        ? el("button", { class: "primary", onclick: () => this._send("resume"), text: "Reanudar" })
        : el("button", { onclick: () => this._send("pause"), text: "Pausar" }));
      const waiting = s.window ? "la ventana de réplica" : s.waiting_for.map((d) => this._name(d.seat)).join(", ");
      row.append(el("button", { disabled: !waiting || s.paused, title: "Aplica la acción por defecto a quien está haciendo esperar", onclick: () => {
        if (confirm(`¿Saltar a ${waiting}? Se aplicará la acción por defecto.`)) this._send("skip");
      }, text: "Saltar espera" }));
      row.append(el("button", { class: "danger", onclick: () => {
        if (confirm("¿Terminar la partida ahora? Ganará quien tenga más cerdos.")) this._send("end");
      }, text: "Terminar partida" }));
    }
    card.append(row);
    return card;
  }

  _screensCard(s) {
    const base = this._base();
    const tvUrl = `${base}${TV_PATH}`;
    const playUrl = joinUrl(base, s.code);
    const card = el("section", { class: "card screens" }, el("h2", { text: "Pantallas" }));
    const line = (label, url) => el("div", { class: "link-row" },
      el("div", {}, el("strong", { text: label }), el("code", { text: url })),
      el("div", { class: "mini" },
        el("button", { onclick: () => navigator.clipboard?.writeText(url).then(() => { this._message = "Copiado."; this._renderStatus(); }), text: "Copiar" }),
        el("a", { href: url, target: "_blank", rel: "noopener", class: "btnlink", text: "Abrir" })));
    card.append(line("TV", tvUrl), line("Jugadores", playUrl),
      el("div", { class: "qr-row" },
        el("img", { src: qrSrc(playUrl), alt: "QR para unirse", width: "132", height: "132" }),
        el("p", { class: "sub" }, "Código ", el("b", { class: "code", text: s.code }),
          ". Abre la URL de la TV en el navegador del televisor; mostrará este QR en grande. Cada jugador entra con su móvil.")));
    const host = new URL(base).hostname;
    if (isLoopbackHost(host)) {
      card.append(el("p", { class: "warn", text: "Estás usando «localhost»: los móviles no podrán entrar. Abre Home Assistant con su IP o define la URL base en las opciones de la integración." }));
    } else if (/nabu\.casa$/.test(host) || (this._info?.local_only && !/^(\d+\.){3}\d+$|\.local$|^\[/.test(host))) {
      card.append(el("p", { class: "warn", text: `Comprueba que «${host}» es accesible desde la red de casa. Con «Solo red local» activo, las conexiones desde fuera se rechazan. Puedes fijar la URL base en las opciones.` }));
    }
    return card;
  }

  _playersCard(s) {
    const card = el("section", { class: "card" }, el("h2", { text: `Jugadores (${s.players.length}/${s.max_players})` }));
    if (!s.players.length) {
      card.append(el("p", { class: "sub", text: "Aún no hay nadie. Pide a los jugadores que escaneen el QR de la TV." }));
      return card;
    }
    const waiting = new Set(s.waiting_for.map((d) => d.seat));
    const list = el("ul", { class: "players" });
    for (const p of s.players) {
      let st = "";
      if (!p.connected) st = "desconectado";
      else if (s.phase === "playing" && p.id === s.active) st = "le toca";
      else if (waiting.has(p.id)) st = "decidiendo";
      list.append(el("li", { class: p.connected ? "" : "off" },
        el("span", { class: "ava", text: p.avatar }),
        el("span", { class: "nm", text: p.name }),
        el("span", { class: "state", text: st }),
        el("span", { class: "sc", text: s.phase === "lobby" ? "" : `${p.pigs} 🐷 · ${p.hand_count} 🂠` }),
        s.phase === "playing" && waiting.has(p.id)
          ? el("button", { class: "icon", title: `Saltar a ${p.name}`, onclick: () => {
            if (confirm(`¿Jugar por defecto por ${p.name}?`)) this._send("skip", { player_id: p.id });
          }, text: "⏭" })
          : el("span"),
        el("button", { class: "icon", title: `Expulsar a ${p.name}`, "aria-label": `Expulsar a ${p.name}`, onclick: () => {
          const extra = s.phase === "playing" ? " Sus cartas irán al monte." : "";
          if (confirm(`¿Expulsar a ${p.name}?${extra}`)) this._send("kick", { player_id: p.id });
        }, text: "✕" })));
    }
    card.append(list);
    return card;
  }

  _configCard(s) {
    const st = s.settings;
    const card = el("section", { class: "card" }, el("h2", { text: "Configuración" }));
    const select = (label, key, values, fmt) => el("label", { class: "field" }, label,
      el("select", { onchange: (ev) => this._send("configure", { settings: { [key]: Number(ev.target.value) } }) },
        values.map((v) => el("option", { value: String(v), selected: v === st[key], text: fmt(v) }))));
    card.append(el("div", { class: "fields" },
      select("Cerdos para ganar", "goal", [0, 4, 5, 6, 7, 8], (v) => (v ? `${v} cerdos` : "Automático (6, o 5 con 5–6 jugadores)")),
      select("Tiempo para replicar", "react_seconds", [0, 5, 8, 12, 15, 20], (v) => (v ? `${v} segundos` : "Sin réplicas (se quitan del mazo)")),
      select("Espera a jugadores desconectados", "absent_seconds", [15, 30, 60, 90, 120], (v) => `${v} segundos`)),
    el("p", { class: "sub", text: "Si alguien pierde la conexión cuando le toca decidir, se espera ese tiempo y luego se juega por defecto (robar, o elegir al azar)." }));
    return card;
  }

  _liveCard(s) {
    const card = el("section", { class: "card" }, el("h2", { text: "En la mesa" }));
    if (s.phase === "finished") {
      const names = s.winners.map((id) => this._name(id)).join(" y ");
      card.append(el("p", { class: "now", text: names ? `Ganador: ${names}` : "Sin ganador." }));
    } else if (s.window) {
      card.append(el("p", { class: "now", text: `${this._name(s.window.actor)} juega ${s.window.card.name}: ventana de réplica abierta.` }));
    } else if (s.waiting_for.length) {
      const d = s.waiting_for[0];
      card.append(el("p", { class: "now", text: `Esperando a ${this._name(d.seat)}: ${d.prompt}` }));
    }
    card.append(el("p", { class: "sub", text: `Meta: ${s.goal} cerdos · mazo: ${s.deck_count} · monte: ${s.discard_count}` }));
    const log = el("ol", { class: "log" });
    for (const e of [...s.log].reverse().slice(0, 10)) log.append(el("li", { text: e.text }));
    card.append(el("h3", { text: "Últimas jugadas" }), log);
    return card;
  }
}

if (!customElements.get("cerditos-locos-panel")) customElements.define("cerditos-locos-panel", CerditosLocosPanel);
