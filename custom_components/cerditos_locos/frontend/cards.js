// Cartas de Cerditos Locos: ilustraciones SVG originales y componentes de carta.
// Todo el texto se inserta con textContent (vía el()); el SVG se construye con el DOM.
import { el } from "./common.js";

const NS = "http://www.w3.org/2000/svg";

export const KIND_LABEL = {
  baby: "Lechón",
  pig: "Cerdo",
  magic_pig: "Cerdo con mañas",
  trick: "Trastada",
  perk: "Chollo",
  pest: "Fastidio",
  neigh: "Réplica",
  super_neigh: "Réplica imbatible",
};
// Etiqueta corta para la franja de color de la carta.
const BAND_LABEL = { ...KIND_LABEL, magic_pig: "Con mañas", super_neigh: "Imbatible" };
export const PIG_KINDS = new Set(["baby", "pig", "magic_pig"]);

// Iconos para las cartas que no son cerdos (texto, sin imágenes externas).
const ICONS = {
  barro: "🛁", cerca: "🚪", mercadillo: "🧺", escapan: "💨", limpieza: "🧹", siesta: "😴",
  charca: "💧", comedero: "🍽️", valla: "🛡️",
  moscas: "🦟", valla_rota: "🔨", pegajoso: "🥾",
  ni_hablar: "✋", ni_hablar_punto: "🛑",
};

// Colores de piel y accesorio por ilustración de cerdo.
const PIGS = {
  lechon: { skin: "#ffc4dc", dark: "#f08fb8" },
  rosado: { skin: "#ff9cc8", dark: "#e46a9f" },
  manchado: { skin: "#ffb3d1", dark: "#e67aa6" },
  rizado: { skin: "#ffa3c4", dark: "#de6b99" },
  coqueta: { skin: "#ffb0d4", dark: "#e977a8" },
  gloton: { skin: "#ff97bf", dark: "#de6494" },
  jabali: { skin: "#a8735a", dark: "#7a4b36" },
  comadrona: { skin: "#ffaccd", dark: "#e5739f" },
  guardian: { skin: "#f59ac0", dark: "#d4699a" },
  carterista: { skin: "#ff9dc4", dark: "#dc6896" },
  tamborilero: { skin: "#ffa8cb", dark: "#e1709e" },
  trufero: { skin: "#f7a3c0", dark: "#d66e95" },
  dormilon: { skin: "#ffb6d3", dark: "#e47ca7" },
};

function s(tag, attrs = {}, ...children) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  for (const c of children) if (c) node.append(c);
  return node;
}

/** Cara de cerdito en SVG (viewBox 100×100). */
export function pigSvg(art, label) {
  const p = PIGS[art] || PIGS.rosado;
  const ink = "#2a1712";
  const svg = s("svg", { viewBox: "0 0 100 100", class: "pig-art", role: "img", "aria-label": label || "Cerdito" });
  const sleepy = art === "dormilon";
  const masked = art === "carterista";
  const baby = art === "lechon";
  const g = s("g", baby ? { transform: "translate(50 58) scale(0.86) translate(-50 -55)" } : {});
  // orejas
  g.append(
    s("path", { d: "M20 38 L26 12 L42 28 Z", fill: p.dark, "stroke-linejoin": "round", stroke: p.dark, "stroke-width": 4 }),
    s("path", { d: "M80 38 L74 12 L58 28 Z", fill: p.dark, "stroke-linejoin": "round", stroke: p.dark, "stroke-width": 4 }),
  );
  // cabeza
  g.append(s("ellipse", { cx: 50, cy: 55, rx: 37, ry: 33, fill: p.skin }));
  if (art === "manchado") g.append(s("ellipse", { cx: 72, cy: 44, rx: 11, ry: 8, fill: "#8a5038", opacity: 0.75 }));
  if (art === "jabali") {
    g.append(s("path", { d: "M30 26 l4 -9 l3 8 l4 -10 l3 9 l4 -10 l3 9 l4 -9 l3 9 l4 -8 l2 10", fill: "none", stroke: p.dark, "stroke-width": 3, "stroke-linecap": "round" }));
  }
  // mofletes
  g.append(
    s("circle", { cx: 25, cy: 64, r: 6, fill: "#ff6fa6", opacity: 0.45 }),
    s("circle", { cx: 75, cy: 64, r: 6, fill: "#ff6fa6", opacity: 0.45 }),
  );
  // antifaz
  if (masked) g.append(s("rect", { x: 20, y: 40, width: 60, height: 15, rx: 7, fill: ink }));
  // ojos
  if (sleepy) {
    g.append(
      s("path", { d: "M31 49 q6 5 12 0", fill: "none", stroke: ink, "stroke-width": 3, "stroke-linecap": "round" }),
      s("path", { d: "M57 49 q6 5 12 0", fill: "none", stroke: ink, "stroke-width": 3, "stroke-linecap": "round" }),
    );
  } else {
    const eye = masked ? "#fff4e6" : ink;
    g.append(s("circle", { cx: 37, cy: 47, r: 4.2, fill: eye }), s("circle", { cx: 63, cy: 47, r: 4.2, fill: eye }));
    if (!masked) g.append(s("circle", { cx: 38.4, cy: 45.6, r: 1.4, fill: "#fff" }), s("circle", { cx: 64.4, cy: 45.6, r: 1.4, fill: "#fff" }));
  }
  // hocico
  g.append(
    s("ellipse", { cx: 50, cy: 66, rx: 15, ry: 10.5, fill: p.dark }),
    s("ellipse", { cx: 44.5, cy: 66, rx: 2.6, ry: 4, fill: ink, opacity: 0.8 }),
    s("ellipse", { cx: 55.5, cy: 66, rx: 2.6, ry: 4, fill: ink, opacity: 0.8 }),
  );
  if (art === "gloton") {
    g.append(s("path", { d: "M43 80 q7 12 14 0 z", fill: "#ff4d6d" }));
  } else {
    g.append(s("path", { d: "M42 80 q8 6 16 0", fill: "none", stroke: ink, "stroke-width": 2.6, "stroke-linecap": "round" }));
  }
  // accesorios
  if (art === "jabali") {
    g.append(
      s("path", { d: "M37 72 l-6 -12 l9 6 z", fill: "#fff8ec" }),
      s("path", { d: "M63 72 l6 -12 l-9 6 z", fill: "#fff8ec" }),
    );
  }
  if (art === "rizado") {
    g.append(s("path", { d: "M40 24 q-4 -10 6 -10 q8 0 4 8 q-3 5 3 4 q8 -2 5 -9", fill: "none", stroke: p.dark, "stroke-width": 3.4, "stroke-linecap": "round" }));
  }
  if (art === "coqueta") {
    g.append(
      s("path", { d: "M66 18 l-10 -8 l0 16 z", fill: "#e8365d" }),
      s("path", { d: "M66 18 l10 -8 l0 16 z", fill: "#e8365d" }),
      s("circle", { cx: 66, cy: 18, r: 3.5, fill: "#ff7b98" }),
    );
  }
  if (art === "comadrona") {
    g.append(
      s("path", { d: "M30 30 q20 -22 40 0 z", fill: "#fffaf2", stroke: "#e4d6c4", "stroke-width": 1.5 }),
      s("rect", { x: 47, y: 15, width: 6, height: 13, fill: "#e8365d" }),
      s("rect", { x: 43.5, y: 18.5, width: 13, height: 6, fill: "#e8365d" }),
    );
  }
  if (art === "guardian") {
    g.append(
      s("path", { d: "M24 34 q26 -34 52 0 z", fill: "#9fb3c8", stroke: "#6d8197", "stroke-width": 2 }),
      s("path", { d: "M50 6 q10 6 4 16 l-8 0 q-4 -10 4 -16 z", fill: "#e8365d" }),
    );
  }
  if (art === "tamborilero") {
    g.append(
      s("rect", { x: 36, y: 6, width: 28, height: 22, rx: 3, fill: "#d93a3a" }),
      s("rect", { x: 34, y: 25, width: 32, height: 5, rx: 2, fill: "#ffc93c" }),
      s("circle", { cx: 50, cy: 6, r: 4, fill: "#ffc93c" }),
    );
  }
  if (art === "trufero") {
    g.append(
      s("path", { d: "M78 84 q8 -14 16 0 z", fill: "#a0522d" }),
      s("rect", { x: 84, y: 83, width: 4, height: 9, rx: 1.5, fill: "#f3e2c7" }),
    );
  }
  if (sleepy) {
    g.append(
      s("path", { d: "M26 30 q24 -30 50 -6 l12 -12 l-4 22 q-30 -14 -58 -4 z", fill: "#5ec8f2" }),
      s("circle", { cx: 88, cy: 12, r: 5, fill: "#fffaf2" }),
    );
    svg.append(s("text", { x: 8, y: 22, "font-size": 16, "font-weight": 700, fill: "#fff4e6", "font-family": "Bungee, sans-serif" }));
    svg.lastChild.textContent = "z";
  }
  if (baby) g.append(s("path", { d: "M47 22 q3 -7 7 -2", fill: "none", stroke: p.dark, "stroke-width": 3, "stroke-linecap": "round" }));
  svg.append(g);
  return svg;
}

/** Ilustración de una carta: cerdito o icono. */
export function artFor(card) {
  if (PIG_KINDS.has(card.kind)) return pigSvg(card.art, card.name);
  return el("span", { class: "icon-art", "aria-hidden": "true", text: ICONS[card.art] || "🃏" });
}

/**
 * Carta completa o en miniatura.
 * opts: size ('full'|'mini'), state ('playable'|'dim'|'selected'), onclick, note
 */
export function cardEl(card, opts = {}) {
  const size = opts.size || "full";
  const cls = ["card", `k-${card.kind}`, size];
  if (opts.state) cls.push(opts.state);
  const tag = opts.onclick ? "button" : "div";
  const props = { class: cls.join(" "), "data-uid": card.uid };
  if (opts.onclick) {
    props.type = "button";
    props.onclick = opts.onclick;
    props["aria-label"] = `${card.name}. ${KIND_LABEL[card.kind]}. ${card.text}`;
    if (opts.state === "selected") props["aria-pressed"] = "true";
  }
  const node = el(tag, props);
  if (size === "mini") {
    node.append(el("span", { class: "art" }, artFor(card)), el("span", { class: "nm", text: card.name }));
    node.title = `${card.name}: ${card.text}`;
  } else {
    node.append(
      el("span", { class: "band", text: BAND_LABEL[card.kind] }),
      el("span", { class: "art" }, artFor(card)),
      el("span", { class: "nm", text: card.name }),
      el("span", { class: "tx", text: card.text }),
    );
  }
  if (opts.note) node.append(el("span", { class: "note", text: opts.note }));
  return node;
}

/** Fila de iconos de cerdito para el progreso hacia la meta. */
export function pigMeter(count, goal) {
  const wrap = el("span", { class: "meter", role: "img", "aria-label": `${count} de ${goal} cerdos` });
  for (let i = 0; i < goal; i++) wrap.append(el("span", { class: i < count ? "dot on" : "dot" }));
  if (count > goal) wrap.append(el("span", { class: "extra", text: `+${count - goal}` }));
  return wrap;
}
