"""Catálogo de cartas: carga y validación de las definiciones en JSON.

Las cartas son datos. Sus efectos se expresan con un vocabulario cerrado de
operaciones (``OPS``) y modificadores permanentes (``MODS``); el motor no ejecuta
código procedente del JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PIG_KINDS = ("baby", "pig", "magic_pig")
PEN_KINDS = PIG_KINDS + ("perk", "pest")
NEIGH_KINDS = ("neigh", "super_neigh")
KINDS = PEN_KINDS + ("trick",) + NEIGH_KINDS

KIND_NAMES = {
    "baby": "Lechón",
    "pig": "Cerdo",
    "magic_pig": "Cerdo con mañas",
    "trick": "Trastada",
    "perk": "Chollo",
    "pest": "Fastidio",
    "neigh": "Réplica",
    "super_neigh": "Réplica imbatible",
}

WHENS = ("play", "enter", "turn_start")
TARGET_OWNERS = ("self", "other", "any")
# op -> claves permitidas además de "op"
OPS: dict[str, set[str]] = {
    "draw": {"n"},
    "discard": {"who", "n"},
    "scare": {"target"},
    "steal_pig": {"target"},
    "return_to_hand": {"target"},
    "remove": {"target"},
    "bring_baby": set(),
    "search_deck": {"kinds"},
    "choose_player": {"filter"},
    "take_random_hand": set(),
    "give_card": set(),
}
TARGETED_OPS = {"scare", "steal_pig", "return_to_hand", "remove"}
MODS: dict[str, set[str]] = {
    "protect": {"from", "scope"},
    "counts_as": {"value"},
    "draw_bonus": {"value"},
    "hand_limit": {"value"},
    "no_react": set(),
    "no_play": {"kinds"},
}
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
MAX_NAME = 32
MAX_TEXT = 140
MAX_COPIES = 12


class CatalogError(ValueError):
    """Definición de carta no válida."""


@dataclass(frozen=True)
class CardDef:
    """Definición inmutable de una carta del catálogo."""

    id: str
    name: str
    kind: str
    copies: int
    text: str
    art: str
    triggers: tuple[dict[str, Any], ...] = ()
    static: tuple[dict[str, Any], ...] = ()

    @property
    def is_pig(self) -> bool:
        return self.kind in PIG_KINDS

    def triggers_for(self, when: str) -> list[dict[str, Any]]:
        return [t for t in self.triggers if t["when"] == when]

    def mods(self, name: str) -> list[dict[str, Any]]:
        return [m for m in self.static if m["mod"] == name]

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "kind": self.kind, "text": self.text, "art": self.art}


@dataclass
class Catalog:
    """Conjunto de definiciones indexadas por id."""

    cards: dict[str, CardDef] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __getitem__(self, card_id: str) -> CardDef:
        return self.cards[card_id]

    def baby_id(self) -> str:
        for c in self.cards.values():
            if c.kind == "baby":
                return c.id
        raise CatalogError("El catálogo no tiene lechones.")

    def deck_size(self, include_neighs: bool = True) -> int:
        return sum(
            c.copies
            for c in self.cards.values()
            if c.kind != "baby" and (include_neighs or c.kind not in NEIGH_KINDS)
        )


def _check_target(target: Any, where: str) -> None:
    if not isinstance(target, dict):
        raise CatalogError(f"{where}: falta el objetivo.")
    if set(target) - {"owner", "kinds"}:
        raise CatalogError(f"{where}: claves de objetivo desconocidas.")
    if target.get("owner") not in TARGET_OWNERS:
        raise CatalogError(f"{where}: dueño de objetivo no válido.")
    kinds = target.get("kinds")
    if not isinstance(kinds, list) or not kinds or not all(k in PEN_KINDS for k in kinds):
        raise CatalogError(f"{where}: tipos de objetivo no válidos.")


def _check_op(op: Any, where: str) -> None:
    if not isinstance(op, dict) or op.get("op") not in OPS:
        raise CatalogError(f"{where}: operación desconocida.")
    name = op["op"]
    extra = set(op) - {"op"} - OPS[name]
    if extra:
        raise CatalogError(f"{where}: claves desconocidas en {name}: {sorted(extra)}.")
    if name in TARGETED_OPS:
        _check_target(op.get("target"), where)
    if name in ("draw", "discard"):
        n = op.get("n")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 5:
            raise CatalogError(f"{where}: n debe estar entre 1 y 5.")
    if name == "discard" and op.get("who") not in ("self", "others", "all"):
        raise CatalogError(f"{where}: who no válido.")
    if name == "search_deck":
        kinds = op.get("kinds")
        if not isinstance(kinds, list) or not kinds or not all(k in KINDS for k in kinds):
            raise CatalogError(f"{where}: tipos de búsqueda no válidos.")
    if name == "choose_player" and op.get("filter") not in ("other", "other_with_hand"):
        raise CatalogError(f"{where}: filtro de jugador no válido.")


def _check_ops_sequence(ops: list[dict[str, Any]], where: str) -> None:
    chosen = False
    for op in ops:
        if op["op"] == "choose_player":
            chosen = True
        if op["op"] in ("take_random_hand", "give_card") and not chosen:
            raise CatalogError(f"{where}: {op['op']} necesita un choose_player antes.")


def _check_mod(mod: Any, where: str) -> None:
    if not isinstance(mod, dict) or mod.get("mod") not in MODS:
        raise CatalogError(f"{where}: modificador desconocido.")
    name = mod["mod"]
    extra = set(mod) - {"mod"} - MODS[name]
    if extra:
        raise CatalogError(f"{where}: claves desconocidas en {name}.")
    if name == "protect":
        if mod.get("from") not in ("scare", "steal") or mod.get("scope") not in ("others", "all"):
            raise CatalogError(f"{where}: protect no válido.")
    if name in ("counts_as", "draw_bonus", "hand_limit"):
        v = mod.get("value")
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 5:
            raise CatalogError(f"{where}: value no válido.")
    if name == "no_play":
        kinds = mod.get("kinds")
        if not isinstance(kinds, list) or not kinds or not all(k in KINDS for k in kinds):
            raise CatalogError(f"{where}: tipos no válidos.")


def parse_card(raw: Any) -> CardDef:
    """Valida una carta y devuelve su definición, o lanza ``CatalogError``."""
    if not isinstance(raw, dict):
        raise CatalogError("La carta no es un objeto.")
    cid = raw.get("id")
    if not isinstance(cid, str) or not ID_RE.match(cid):
        raise CatalogError(f"Id no válido: {cid!r}.")
    where = f"Carta {cid}"
    allowed = {"id", "name", "type", "copies", "art", "text", "triggers", "static"}
    if set(raw) - allowed:
        raise CatalogError(f"{where}: claves desconocidas {sorted(set(raw) - allowed)}.")
    name, kind, text, art = raw.get("name"), raw.get("type"), raw.get("text"), raw.get("art", cid)
    if not isinstance(name, str) or not 1 <= len(name) <= MAX_NAME:
        raise CatalogError(f"{where}: nombre no válido.")
    if kind not in KINDS:
        raise CatalogError(f"{where}: tipo no válido.")
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT:
        raise CatalogError(f"{where}: texto no válido.")
    if not isinstance(art, str) or not ID_RE.match(art):
        raise CatalogError(f"{where}: arte no válido.")
    copies = raw.get("copies")
    if not isinstance(copies, int) or isinstance(copies, bool) or not 1 <= copies <= MAX_COPIES:
        raise CatalogError(f"{where}: copias no válidas.")
    triggers = raw.get("triggers", [])
    static = raw.get("static", [])
    if not isinstance(triggers, list) or not isinstance(static, list):
        raise CatalogError(f"{where}: triggers/static deben ser listas.")
    for t in triggers:
        if not isinstance(t, dict) or t.get("when") not in WHENS:
            raise CatalogError(f"{where}: disparador no válido.")
        if set(t) - {"when", "optional", "do"}:
            raise CatalogError(f"{where}: claves de disparador desconocidas.")
        if not isinstance(t.get("optional", False), bool):
            raise CatalogError(f"{where}: optional debe ser booleano.")
        ops = t.get("do")
        if not isinstance(ops, list) or not ops:
            raise CatalogError(f"{where}: disparador sin operaciones.")
        for op in ops:
            _check_op(op, where)
        _check_ops_sequence(ops, where)
        if t["when"] == "play" and kind != "trick":
            raise CatalogError(f"{where}: solo las trastadas usan 'play'.")
        if t["when"] != "play" and kind == "trick":
            raise CatalogError(f"{where}: las trastadas solo usan 'play'.")
    for m in static:
        _check_mod(m, where)
    if kind in ("baby", "pig", "neigh", "super_neigh") and (triggers or static):
        raise CatalogError(f"{where}: este tipo de carta no tiene efectos.")
    return CardDef(
        id=cid,
        name=name,
        kind=kind,
        copies=copies,
        text=text,
        art=art,
        triggers=tuple(triggers),
        static=tuple(static),
    )


def parse_catalog(data: Any) -> Catalog:
    """Valida un catálogo completo. Las cartas inválidas se descartan con aviso."""
    catalog = Catalog()
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise CatalogError("El catálogo debe tener una lista 'cards'.")
    for raw in data["cards"]:
        try:
            card = parse_card(raw)
        except CatalogError as err:
            catalog.warnings.append(str(err))
            continue
        if card.id in catalog.cards:
            catalog.warnings.append(f"Carta {card.id}: id duplicado, se ignora.")
            continue
        catalog.cards[card.id] = card
    kinds = {c.kind for c in catalog.cards.values()}
    if "baby" not in kinds:
        raise CatalogError("El catálogo necesita lechones.")
    if not kinds & {"pig", "magic_pig"}:
        raise CatalogError("El catálogo necesita cerdos.")
    return catalog


def load_catalog(path: Path) -> Catalog:
    """Lee y valida un catálogo desde disco (bloqueante)."""
    return parse_catalog(json.loads(path.read_text(encoding="utf-8")))
