"""Motor de Cerditos Locos: estado autoritativo, turnos, efectos, réplicas y victoria.

Puro Python: sin E/S ni asyncio. El tiempo llega de un reloj inyectable y las
transiciones por tiempo (ventana de réplica, jugadores ausentes) se aplican con
``tick()``.

Modelo de ejecución
-------------------
La partida es una **pila de trabajo** (``self.work``) de tareas serializables
(diccionarios). El bucle ``_run`` ejecuta siempre la tarea de arriba:

- ``done``: la tarea ha terminado y se retira (puede haber apilado otras encima).
- ``again``: sigue en la pila; se vuelve a ejecutar (normalmente tras apilar otras).
- ``block``: hace falta una decisión de algún jugador o la ventana de réplica está
  abierta. El motor se detiene hasta recibir la acción correspondiente.

Las tareas de fase (inicio de turno, robo, acción, final) marcan los momentos en
que no hay ningún efecto a medio resolver: ahí se comprueba la victoria.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from . import effects
from .catalog import NEIGH_KINDS, PIG_KINDS, Catalog, CardDef
from .names import AVATARS, InvalidName, name_key, normalize_name, validate_avatar

MIN_PLAYERS = 2
MAX_PLAYERS = 6
HAND_SIZE = 5
BASE_HAND_LIMIT = 7
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LEN = 4
LOG_KEEP = 40
MAX_LOOP_STEPS = 10_000

LIMITS = {
    "goal": (0, 8),  # 0 = automático según el número de jugadores
    "react_seconds": (0, 20),  # 0 = sin réplicas
    "absent_seconds": (10, 120),
}
PHASE_TASKS = {"turn_start", "draw_phase", "action", "end_phase", "next_turn"}


class Phase(str, Enum):
    """Fases de la partida."""

    LOBBY = "lobby"
    PLAYING = "playing"
    FINISHED = "finished"


class GameError(Exception):
    """Acción rechazada. ``message`` está en español y se puede mostrar al usuario."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def auto_goal(num_players: int) -> int:
    """Cerdos necesarios para ganar según el número de jugadores."""
    return 6 if num_players <= 4 else 5


@dataclass
class Settings:
    """Configuración de partida elegida por el anfitrión."""

    goal: int = 0
    react_seconds: int = 8
    absent_seconds: int = 30

    def as_dict(self) -> dict[str, Any]:
        return {"goal": self.goal, "react_seconds": self.react_seconds, "absent_seconds": self.absent_seconds}


@dataclass
class Seat:
    """Jugador sentado a la mesa."""

    id: str
    name: str
    avatar: str
    order: int
    connected: bool = True
    hand: list[str] = field(default_factory=list)
    pen: list[str] = field(default_factory=list)


@dataclass
class Decision:
    """Elección pendiente de un jugador.

    kind: ``turn`` (jugar o robar), ``yes_no``, ``cards`` (elegir cartas de ``options``),
    ``discard`` (descartar de la mano), ``player`` (elegir un jugador).
    """

    id: str
    seat: str
    kind: str
    prompt: str
    options: list[str] = field(default_factory=list)
    min: int = 0
    max: int = 0
    source: str | None = None
    deadline: float | None = None
    answer: Any = None
    answered: bool = False


@dataclass
class Window:
    """Ventana de réplica abierta tras jugar una carta desde la mano."""

    id: str
    card: str
    actor: str
    last: str
    chain: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    deadline: float | None = None
    duration: float = 0.0


class Game:
    """Partida única gestionada por el servidor."""

    def __init__(
        self,
        catalog: Catalog,
        clock: Callable[[], float],
        rng: random.Random | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.catalog = catalog
        self._clock = clock
        self.rng = rng or random.Random(secrets.randbits(64))
        self.settings = settings or Settings()
        self.seats: dict[str, Seat] = {}
        self.order: list[str] = []
        self._join_counter = 0
        self._id_counter = 0
        self.code = ""
        self.phase = Phase.LOBBY
        self.paused = False
        self._paused_at: float | None = None
        self.cards: dict[str, str] = {}  # uid -> id de definición
        self.deck: list[str] = []
        self.discard: list[str] = []
        self.nursery: list[str] = []
        self.limbo: list[str] = []  # cartas jugadas que se están resolviendo
        self.work: list[dict[str, Any]] = []
        self.pending: list[Decision] = []
        self.window: Window | None = None
        self.active: str | None = None
        self.turn = 0
        self.goal = 0
        self.winners: list[str] = []
        self.end_reason: str | None = None
        self.log: list[dict[str, Any]] = []
        self._log_seq = 0
        self.version = 0
        self._events: list[tuple[str, dict[str, Any]]] = []
        self._new_code()

    # ------------------------------------------------------------------ utilidades
    def now(self) -> float:
        return self._clock()

    def _changed(self) -> None:
        self.version += 1

    def emit(self, event: str, /, **data: Any) -> None:
        self._events.append((event, data))

    def pop_events(self) -> list[tuple[str, dict[str, Any]]]:
        events, self._events = self._events, []
        return events

    def _new_code(self) -> None:
        self.code = "".join(self.rng.choice(CODE_ALPHABET) for _ in range(CODE_LEN))

    def next_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}{self._id_counter}"

    def say(self, text: str) -> None:
        if text.endswith(("!.", "?.")):  # «… con ¡Ni hablar!.» → «… con ¡Ni hablar!»
            text = text[:-1]
        self._log_seq += 1
        self.log.append({"n": self._log_seq, "text": text})
        del self.log[:-LOG_KEEP]

    def card(self, uid: str) -> CardDef:
        return self.catalog[self.cards[uid]]

    def cname(self, uid: str) -> str:
        return self.card(uid).name

    def seat(self, sid: str) -> Seat:
        seat = self.seats.get(sid)
        if seat is None:
            raise GameError("unknown_player", "Ese jugador ya no está en la partida.")
        return seat

    def owner_of(self, uid: str) -> str | None:
        for s in self.seats.values():
            if uid in s.pen:
                return s.id
        return None

    def others(self, sid: str) -> list[str]:
        """Rivales en orden de juego, empezando por el siguiente a ``sid``."""
        if sid not in self.order:
            return [o for o in self.order if o != sid]
        i = self.order.index(sid)
        return [self.order[(i + k) % len(self.order)] for k in range(1, len(self.order))]

    # ------------------------------------------------------------------ reglas derivadas
    def pig_count(self, sid: str) -> int:
        total = 0
        for uid in self.seats[sid].pen:
            c = self.card(uid)
            if c.is_pig:
                mods = c.mods("counts_as")
                total += mods[0]["value"] if mods else 1
        return total

    def _pen_mods(self, sid: str, name: str) -> list[tuple[str, dict[str, Any]]]:
        return [(uid, m) for uid in self.seats[sid].pen for m in self.card(uid).mods(name)]

    def hand_limit(self, sid: str) -> int:
        return BASE_HAND_LIMIT + sum(m["value"] for _, m in self._pen_mods(sid, "hand_limit"))

    def draw_amount(self, sid: str) -> int:
        return 1 + sum(m["value"] for _, m in self._pen_mods(sid, "draw_bonus"))

    def can_react(self, sid: str) -> bool:
        return not self._pen_mods(sid, "no_react")

    def blocked_kinds(self, sid: str) -> set[str]:
        return {k for _, m in self._pen_mods(sid, "no_play") for k in m["kinds"]}

    def is_protected(self, uid: str, action: str) -> bool:
        """True si la carta de una pocilga está protegida frente a ``scare`` o ``steal``."""
        owner = self.owner_of(uid)
        if owner is None:
            return False
        for src, m in self._pen_mods(owner, "protect"):
            if m["from"] != action:
                continue
            if m["scope"] == "all" or src != uid:
                return True
        return False

    def reactions_enabled(self) -> bool:
        return self.settings.react_seconds > 0

    # ------------------------------------------------------------------ jugadores
    def add_player(self, raw_name: Any, raw_avatar: Any = None) -> Seat:
        if self.phase != Phase.LOBBY:
            raise GameError("game_running", "La partida ya ha empezado. Espera a la siguiente.")
        try:
            name = normalize_name(raw_name)
            avatar = validate_avatar(raw_avatar)
        except InvalidName as err:
            raise GameError(err.code, err.message) from err
        if len(self.seats) >= MAX_PLAYERS:
            raise GameError("room_full", f"La pocilga está llena (máximo {MAX_PLAYERS}).")
        key = name_key(name)
        if any(name_key(s.name) == key for s in self.seats.values()):
            raise GameError("name_taken", "Ese nombre ya está en uso. Prueba con otro.")
        used = {s.avatar for s in self.seats.values()}
        if avatar is None or avatar in used:
            free = [a for a in AVATARS if a not in used] or list(AVATARS)
            avatar = self.rng.choice(free)
        self._join_counter += 1
        sid = f"p{self._join_counter}"
        seat = Seat(sid, name, avatar, self._join_counter)
        self.seats[sid] = seat
        self.emit("player_joined", player_id=sid, name=name)
        self._changed()
        return seat

    def set_connected(self, sid: str, connected: bool) -> None:
        seat = self.seats.get(sid)
        if seat is None or seat.connected == connected:
            return
        seat.connected = connected
        for d in self.pending:
            if d.seat == sid and not d.answered:
                d.deadline = None if connected else self._absent_deadline()
        self._changed()
        if self.phase == Phase.PLAYING and self.window is not None and not connected:
            self._maybe_close_window()
            self._run()

    def _absent_deadline(self) -> float | None:
        if self.paused:
            return None
        return self.now() + self.settings.absent_seconds

    def remove_player(self, sid: str) -> None:
        """Expulsión o abandono. En partida, sus cartas salen del juego."""
        seat = self.seat(sid)
        if self.phase != Phase.PLAYING:
            del self.seats[sid]
            if sid in self.order:
                self.order.remove(sid)
            self._changed()
            return
        self.say(f"{seat.name} deja la partida.")
        if self.active == sid:
            self._abort_turn()
        else:
            # Responde por defecto lo que tenga pendiente antes de retirarlo.
            for _ in range(20):
                mine = [d for d in self.pending if d.seat == sid and not d.answered]
                if not mine:
                    break
                for d in mine:
                    self._answer(d, self._default_answer(d))
                self._after_answer()
        for uid in list(seat.hand):
            self._move(uid, self.discard)
        for uid in list(seat.pen):
            self._leave_pen(uid)
        del self.seats[sid]
        self.order.remove(sid)
        self._prune_pending(sid)
        if self.window is not None:
            if self.window.last == sid:
                self.window.last = ""
            self._maybe_close_window()
        self._changed()
        if len(self.order) < MIN_PLAYERS:
            self._finish("players", list(self.order))
            return
        self._run()

    def _prune_pending(self, sid: str) -> None:
        """Quita de las decisiones pendientes las opciones que ya no existen."""
        in_pens = {u for s in self.seats.values() for u in s.pen}
        for d in self.pending:
            if d.answered:
                continue
            if d.kind == "player":
                d.options = [o for o in d.options if o in self.seats]
            elif d.kind == "cards":
                hand = set(self.seats[d.seat].hand)
                d.options = [u for u in d.options if u in in_pens or u in hand or u in self.deck]
            if len(d.options) < d.min:
                self._answer(d, None if d.kind == "player" else [])
        self._after_answer()

    def _abort_turn(self) -> None:
        """Corta el turno en curso (el jugador activo ha salido)."""
        for uid in list(self.limbo):
            self._move(uid, self.discard)
        self.window = None
        self.pending = []
        assert self.active is not None
        nxt = self.others(self.active)
        self.work = [{"k": "next_turn", "to": nxt[0] if nxt else None}]

    # ------------------------------------------------------------------ anfitrión
    def configure(self, data: dict[str, Any]) -> None:
        if self.phase != Phase.LOBBY:
            raise GameError("wrong_phase", "Solo se puede configurar antes de empezar.")
        new = Settings(**self.settings.__dict__)
        for key in LIMITS:
            if key in data:
                value = data[key]
                if not isinstance(value, int) or isinstance(value, bool):
                    raise GameError("invalid_settings", f"Valor no válido para {key}.")
                lo, hi = LIMITS[key]
                value = max(lo, min(hi, value))
                if key == "goal" and 0 < value < 3:
                    value = 3
                if key == "react_seconds" and 0 < value < 4:
                    value = 4
                setattr(new, key, value)
        self.settings = new
        self._changed()

    def start(self) -> None:
        if self.phase != Phase.LOBBY:
            raise GameError("wrong_phase", "La partida ya ha empezado.")
        connected = [s for s in self.seats.values() if s.connected]
        if len(connected) < MIN_PLAYERS:
            raise GameError("not_enough_players", f"Se necesitan al menos {MIN_PLAYERS} jugadores.")
        # Los desconectados en la sala de espera no entran en la partida.
        self.seats = {s.id: s for s in connected}
        for s in self.seats.values():
            s.hand.clear()
            s.pen.clear()
        self.cards = {}
        self.deck, self.discard, self.nursery, self.limbo = [], [], [], []
        include_neighs = self.reactions_enabled()
        for c in self.catalog.cards.values():
            if c.kind in NEIGH_KINDS and not include_neighs:
                continue
            for _ in range(c.copies):
                uid = self.next_id("c")
                self.cards[uid] = c.id
                (self.nursery if c.kind == "baby" else self.deck).append(uid)
        self.rng.shuffle(self.deck)
        self.order = [s.id for s in sorted(self.seats.values(), key=lambda s: s.order)]
        self.rng.shuffle(self.order)
        for sid in self.order:
            if self.nursery:
                self.seats[sid].pen.append(self.nursery.pop())
            for _ in range(HAND_SIZE):
                if self.deck:
                    self.seats[sid].hand.append(self.deck.pop())
        self.goal = self.settings.goal or auto_goal(len(self.order))
        self.phase = Phase.PLAYING
        self.paused = False
        self.winners = []
        self.end_reason = None
        self.pending = []
        self.window = None
        self.turn = 0
        self.log = []
        self.active = self.order[0]
        self.work = [{"k": "turn_start"}]
        self.say(f"¡Empieza la partida! Gana quien junte {self.goal} cerdos. Abre {self.seats[self.active].name}.")
        self.emit("game_started", goal=self.goal, players=len(self.order))
        self._changed()
        self._run()

    def pause(self) -> None:
        if self.phase != Phase.PLAYING:
            raise GameError("wrong_phase", "No hay partida en curso.")
        if self.paused:
            return
        self.paused = True
        self._paused_at = self.now()
        self._changed()

    def resume(self) -> None:
        if not self.paused:
            return
        delta = self.now() - (self._paused_at or self.now())
        self.paused = False
        self._paused_at = None
        if self.window is not None and self.window.deadline is not None:
            self.window.deadline += delta
        for d in self.pending:
            if d.deadline is not None:
                d.deadline += delta
            elif not self.seats[d.seat].connected and not d.answered:
                d.deadline = self._absent_deadline()
        self._changed()

    def skip(self, sid: str | None = None) -> None:
        """El anfitrión aplica la acción por defecto a quien esté haciendo esperar."""
        self._require_playing()
        targets = [d for d in self.pending if not d.answered and (sid is None or d.seat == sid)]
        if not targets and self.window is None:
            raise GameError("nothing_to_skip", "No hay nadie a quien saltar ahora.")
        if not targets:
            self.say("El anfitrión cierra la ventana de réplica.")
            self._close_window()
            self._run()
            return
        for d in targets:
            self.say(f"El anfitrión salta a {self.seats[d.seat].name}.")
            self._answer(d, self._default_answer(d))
        self._changed()
        self._after_answer()

    def end(self) -> None:
        if self.phase == Phase.FINISHED:
            return
        if self.phase == Phase.LOBBY:
            raise GameError("wrong_phase", "La partida no ha empezado.")
        leaders = self._leaders(list(self.order))
        self._finish("host", leaders)

    def new_game(self, keep_players: bool = True) -> None:
        self.phase = Phase.LOBBY
        self.paused = False
        self.work, self.pending, self.window = [], [], None
        self.cards, self.deck, self.discard, self.nursery, self.limbo = {}, [], [], [], []
        self.active = None
        self.winners = []
        self.end_reason = None
        self.order = []
        self.log = []
        if keep_players:
            self.seats = {sid: s for sid, s in self.seats.items() if s.connected}
            for s in self.seats.values():
                s.hand.clear()
                s.pen.clear()
        else:
            self.seats = {}
        self._new_code()
        self.emit("new_game")
        self._changed()

    # ------------------------------------------------------------------ acciones de jugador
    def _require_playing(self) -> None:
        if self.phase != Phase.PLAYING:
            raise GameError("wrong_phase", "No hay partida en curso.")

    def _require_unpaused(self) -> None:
        if self.paused:
            raise GameError("paused", "La partida está en pausa.")

    def _turn_decision(self, sid: str) -> Decision:
        for d in self.pending:
            if d.kind == "turn" and d.seat == sid and not d.answered:
                return d
        raise GameError("not_your_turn", "Ahora no es tu turno de jugar.")

    def legal_plays(self, sid: str) -> dict[str, list[str] | None]:
        """Cartas que ``sid`` puede jugar ahora: uid -> opciones de objetivo (o None)."""
        if self.phase != Phase.PLAYING or not any(
            d.kind == "turn" and d.seat == sid and not d.answered for d in self.pending
        ):
            return {}
        blocked = self.blocked_kinds(sid)
        plays: dict[str, list[str] | None] = {}
        for uid in self.seats[sid].hand:
            kind = self.card(uid).kind
            if kind in NEIGH_KINDS or kind in blocked or kind == "baby":
                continue
            if kind == "pest":
                plays[uid] = self.others(sid)
            else:
                plays[uid] = None
        return plays

    def play(self, sid: str, uid: Any, target: Any = None) -> None:
        self._require_playing()
        self._require_unpaused()
        d = self._turn_decision(sid)
        if not isinstance(uid, str) or uid not in self.seats[sid].hand:
            raise GameError("not_in_hand", "Esa carta no está en tu mano.")
        plays = self.legal_plays(sid)
        if uid not in plays:
            kind = self.card(uid).kind
            if kind in NEIGH_KINDS:
                raise GameError("not_playable", "Las réplicas solo se juegan cuando otro jugador juega una carta.")
            raise GameError("not_playable", "Ahora no puedes jugar esa carta.")
        targets = plays[uid]
        if targets is not None and target not in targets:
            raise GameError("bad_target", "Elige a qué rival se lo pones.")
        self._answer(d, {"play": uid, "target": target if targets is not None else None})
        self._changed()
        self._after_answer()

    def draw_instead(self, sid: str) -> None:
        self._require_playing()
        self._require_unpaused()
        d = self._turn_decision(sid)
        self._answer(d, {"draw": True})
        self._changed()
        self._after_answer()

    def decide(self, sid: str, decision_id: Any, choice: Any) -> None:
        self._require_playing()
        self._require_unpaused()
        d = next((x for x in self.pending if x.id == decision_id and not x.answered), None)
        if d is None:
            raise GameError("stale_decision", "Esa decisión ya no está activa.")
        if d.seat != sid:
            raise GameError("not_yours", "Esa decisión no es tuya.")
        if d.kind == "turn":
            raise GameError("bad_decision", "Usa jugar o robar.")
        self._answer(d, self._validate_choice(d, choice))
        self._changed()
        self._after_answer()

    def _validate_choice(self, d: Decision, choice: Any) -> Any:
        if d.kind == "yes_no":
            if not isinstance(choice, bool):
                raise GameError("bad_choice", "Respuesta no válida.")
            return choice
        if d.kind == "player":
            if choice not in d.options:
                raise GameError("bad_choice", "Elige uno de los jugadores propuestos.")
            return choice
        # cards / discard: lista de uids sin repetir
        if not isinstance(choice, list) or not all(isinstance(c, str) for c in choice):
            raise GameError("bad_choice", "Selección no válida.")
        if len(set(choice)) != len(choice) or not set(choice) <= set(d.options):
            raise GameError("bad_choice", "Selección no válida.")
        if not d.min <= len(choice) <= d.max:
            if d.min == d.max:
                raise GameError("bad_choice", f"Elige exactamente {d.min}.")
            raise GameError("bad_choice", f"Elige entre {d.min} y {d.max}.")
        return choice

    def react(self, sid: str, window_id: Any, uid: Any) -> None:
        self._require_playing()
        self._require_unpaused()
        w = self.window
        if w is None or w.id != window_id:
            raise GameError("stale_window", "Ya no se puede replicar a esa jugada.")
        if sid not in self.eligible_reactors():
            if uid is None:
                return
            raise GameError("cannot_react", "No puedes replicar ahora.")
        if uid is None:
            if sid not in w.passed:
                w.passed.append(sid)
            self._changed()
            self._maybe_close_window()
            self._run()
            return
        if not isinstance(uid, str) or uid not in self.seats[sid].hand:
            raise GameError("not_in_hand", "Esa carta no está en tu mano.")
        kind = self.card(uid).kind
        if kind not in NEIGH_KINDS:
            raise GameError("not_reaction", "Esa carta no es una réplica.")
        if not self.can_react(sid):
            raise GameError("cannot_react", "Las moscas no te dejan replicar.")
        self._move(uid, self.limbo)
        w.chain.append(uid)
        self.say(f"{self.seats[sid].name} replica con {self.cname(uid)}.")
        self.emit("reacted", player_id=sid, card=self.cards[uid])
        if kind == "super_neigh":
            self._changed()
            self._close_window()
        else:
            w.id = self.next_id("w")
            w.last = sid
            w.passed = []
            w.deadline = None if self.paused else self.now() + self.settings.react_seconds
            self._changed()
            self._maybe_close_window()
        self._run()

    # ------------------------------------------------------------------ decisiones
    def ask(
        self,
        sid: str,
        kind: str,
        prompt: str,
        options: list[str] | None = None,
        lo: int = 0,
        hi: int = 0,
        source: str | None = None,
    ) -> str:
        d = Decision(
            id=self.next_id("d"),
            seat=sid,
            kind=kind,
            prompt=prompt,
            options=list(options or []),
            min=lo,
            max=hi,
            source=source,
        )
        if not self.seats[sid].connected:
            d.deadline = self._absent_deadline()
        self.pending.append(d)
        return d.id

    def _answer(self, d: Decision, answer: Any) -> None:
        d.answer = answer
        d.answered = True
        d.deadline = None

    def _after_answer(self) -> None:
        if self.pending and all(d.answered for d in self.pending):
            answers = {d.id: d.answer for d in self.pending}
            self.pending = []
            if self.work:
                self.work[-1].setdefault("ans", {}).update(answers)
            self._run()

    def _default_answer(self, d: Decision) -> Any:
        if d.kind == "turn":
            return {"draw": True}
        if d.kind == "yes_no":
            return False
        if d.kind == "player":
            return self.rng.choice(d.options)
        n = d.min
        return self.rng.sample(d.options, n) if n else []

    # ------------------------------------------------------------------ réplicas
    def eligible_reactors(self) -> list[str]:
        w = self.window
        if w is None:
            return []
        return [sid for sid in self.order if sid != w.last and self.seats[sid].connected]

    def _open_window(self, uid: str, sid: str) -> bool:
        if not self.reactions_enabled():
            return False
        self.window = Window(
            id=self.next_id("w"),
            card=uid,
            actor=sid,
            last=sid,
            deadline=None if self.paused else self.now() + self.settings.react_seconds,
            duration=float(self.settings.react_seconds),
        )
        if not self.eligible_reactors():
            self.window = None
            return False
        return True

    def _maybe_close_window(self) -> None:
        w = self.window
        if w is None:
            return
        if all(sid in w.passed for sid in self.eligible_reactors()):
            self._close_window()

    def _close_window(self) -> None:
        w = self.window
        if w is None:
            return
        self.window = None
        cancelled = len(w.chain) % 2 == 1
        for uid in w.chain:
            self._move(uid, self.discard)
        if self.work and self.work[-1].get("k") == "play" and self.work[-1].get("uid") == w.card:
            self.work[-1]["cancelled"] = cancelled
            self.work[-1]["stage"] = "resolve"
        self._changed()

    # ------------------------------------------------------------------ movimientos
    def _zone_of(self, uid: str) -> list[str]:
        for zone in (self.deck, self.discard, self.nursery, self.limbo):
            if uid in zone:
                return zone
        for s in self.seats.values():
            if uid in s.hand:
                return s.hand
            if uid in s.pen:
                return s.pen
        raise KeyError(uid)

    def _move(self, uid: str, dest: list[str]) -> None:
        self._zone_of(uid).remove(uid)
        dest.append(uid)

    def _leave_pen(self, uid: str, dest: list[str] | None = None) -> None:
        """Saca una carta de una pocilga: los lechones siempre vuelven al corral."""
        if self.card(uid).kind == "baby":
            self._move(uid, self.nursery)
        else:
            self._move(uid, self.discard if dest is None else dest)

    def enter_pen(self, uid: str, sid: str) -> None:
        """Pone una carta en una pocilga y apila sus efectos de entrada."""
        self._move(uid, self.seats[sid].pen)
        for i, _ in enumerate(self.card(uid).triggers_for("enter")):
            self.work.append({"k": "trigger", "src": uid, "seat": sid, "when": "enter", "i": i})

    def draw(self, sid: str, n: int) -> bool:
        """Roba ``n`` cartas. Si el mazo se agota, termina la partida y devuelve False."""
        for _ in range(n):
            if not self.deck:
                self.say("¡Se acabó el mazo!")
                self._finish("deck", self._leaders(list(self.order)))
                return False
            self.seats[sid].hand.append(self.deck.pop())
        return True

    # ------------------------------------------------------------------ bucle de ejecución
    def _run(self) -> None:
        steps = 0
        while self.phase == Phase.PLAYING and self.work and not self.pending and self.window is None:
            steps += 1
            if steps > MAX_LOOP_STEPS:  # pragma: no cover - protección
                raise RuntimeError("Bucle de resolución sin fin")
            task = self.work[-1]
            if task["k"] in PHASE_TASKS and self._check_win():
                return
            result = self._step(task)
            if self.phase != Phase.PLAYING:
                return
            if result == "done":
                for i in range(len(self.work) - 1, -1, -1):
                    if self.work[i] is task:
                        del self.work[i]
                        break
            elif result == "block":
                break
        self._changed()

    def _step(self, task: dict[str, Any]) -> str:
        handler = getattr(self, f"_task_{task['k']}")
        return handler(task)

    # ---- tareas de fase
    def _task_turn_start(self, task: dict[str, Any]) -> str:
        sid = self.active
        assert sid is not None
        if not task.get("queued"):
            task["queued"] = True
            self.emit("turn_started", player_id=sid, turn=self.turn)
            # Debajo de los disparos queda la fase de robo.
            self.work.insert(len(self.work) - 1, {"k": "draw_phase"})
            for uid in reversed(list(self.seats[sid].pen)):
                for i in reversed(range(len(self.card(uid).triggers_for("turn_start")))):
                    self.work.append({"k": "trigger", "src": uid, "seat": sid, "when": "turn_start", "i": i})
            return "again"
        return "done"

    def _task_draw_phase(self, task: dict[str, Any]) -> str:
        sid = self.active
        assert sid is not None
        if not self.draw(sid, self.draw_amount(sid)):
            return "block"
        self.work.insert(len(self.work) - 1, {"k": "action"})
        return "done"

    def _task_action(self, task: dict[str, Any]) -> str:
        sid = self.active
        assert sid is not None
        ans = task.get("ans")
        if not ans:
            self.ask(sid, "turn", "Juega una carta o roba otra.")
            return "block"
        answer = next(iter(ans.values()))
        seat = self.seats[sid]
        self.work.insert(len(self.work) - 1, {"k": "end_phase"})
        if answer.get("draw"):
            self.say(f"{seat.name} prefiere robar otra carta.")
            self.emit("drew_instead", player_id=sid)
            self.draw(sid, 1)
            return "done"
        uid = answer["play"]
        self.work[-1] = {"k": "play", "uid": uid, "seat": sid, "target": answer.get("target")}
        return "again"

    def _task_end_phase(self, task: dict[str, Any]) -> str:
        sid = self.active
        assert sid is not None
        seat = self.seats[sid]
        ans = task.get("ans")
        if ans:
            chosen = next(iter(ans.values()))
            for uid in chosen:
                self._move(uid, self.discard)
            self.say(f"{seat.name} descarta {len(chosen)} carta(s) por pasarse del límite.")
        else:
            extra = len(seat.hand) - self.hand_limit(sid)
            if extra > 0:
                self.ask(sid, "discard", f"Tienes demasiadas cartas: descarta {extra}.", list(seat.hand), extra, extra)
                return "block"
        self.work.insert(len(self.work) - 1, {"k": "next_turn"})
        return "done"

    def _task_next_turn(self, task: dict[str, Any]) -> str:
        if task.get("to") in self.order:
            self.active = task["to"]
        elif self.active in self.order:
            i = self.order.index(self.active)
            self.active = self.order[(i + 1) % len(self.order)]
        else:
            self.active = self.order[0]
        self.turn += 1
        self.work.insert(len(self.work) - 1, {"k": "turn_start"})
        return "done"

    # ---- jugar una carta
    def _task_play(self, task: dict[str, Any]) -> str:
        uid, sid = task["uid"], task["seat"]
        c = self.card(uid)
        name = self.seats[sid].name
        stage = task.get("stage")
        if stage is None:
            self._move(uid, self.limbo)
            target = task.get("target")
            extra = f" a {self.seats[target].name}" if target in self.seats else ""
            self.say(f"{name} juega {c.name}{extra}.")
            self.emit("card_played", player_id=sid, card=c.id, target=target)
            task["stage"] = "window"
            if self._open_window(uid, sid):
                return "block"
            task["stage"] = "resolve"
            task["cancelled"] = False
            return "again"
        if stage == "window":  # pragma: no cover - la ventana fija el estado al cerrar
            return "block"
        if task.get("cancelled"):
            self._move(uid, self.discard)
            self.say(f"{c.name} de {name} queda anulada.")
            self.emit("card_cancelled", player_id=sid, card=c.id)
            return "done"
        if stage == "resolve":
            task["stage"] = "effects"
            if c.kind in PIG_KINDS:
                self.enter_pen(uid, sid)
                self.say(f"{c.name} entra en la pocilga de {name}.")
            elif c.kind == "perk":
                self.enter_pen(uid, sid)
            elif c.kind == "pest":
                target = task.get("target")
                if target not in self.seats:  # el rival se fue mientras tanto
                    self._move(uid, self.discard)
                    self.say(f"{c.name} se queda sin destinatario.")
                else:
                    self.enter_pen(uid, target)
                    self.say(f"{c.name} llega a la pocilga de {self.seats[target].name}.")
            elif c.kind == "trick":
                # Queda en juego hasta terminar de resolverse; después va a El Monte.
                self.work.append({"k": "to_discard", "uid": uid})
                for i in reversed(range(len(c.triggers_for("play")))):
                    self.work.append({"k": "trigger", "src": uid, "seat": sid, "when": "play", "i": i})
            return "again"
        return "done"

    def _task_to_discard(self, task: dict[str, Any]) -> str:
        if task["uid"] in self.limbo:
            self._move(task["uid"], self.discard)
        return "done"

    # ---- disparos y operaciones
    def _task_trigger(self, task: dict[str, Any]) -> str:
        uid, sid = task["src"], task["seat"]
        if sid not in self.seats:
            return "done"
        # Un efecto de pocilga solo actúa si la carta sigue allí.
        if task["when"] in ("enter", "turn_start") and uid not in self.seats[sid].pen:
            return "done"
        trig = self.card(uid).triggers_for(task["when"])[task["i"]]
        if trig.get("optional") and "ok" not in task:
            ans = task.get("ans")
            if ans:
                task["ok"] = bool(next(iter(ans.values())))
                task.pop("ans")
            else:
                if not effects.has_effect(self, trig["do"][0], sid):
                    return "done"
                self.ask(sid, "yes_no", f"¿Usar {self.cname(uid)}? {self.card(uid).text}", source=uid)
                return "block"
            if not task["ok"]:
                return "done"
        self.work[-1] = {"k": "ops", "ops": trig["do"], "i": 0, "seat": sid, "src": uid, "ctx": {}}
        return "again"

    def _task_ops(self, task: dict[str, Any]) -> str:
        while task["i"] < len(task["ops"]):
            if task["ctx"].get("abort"):
                return "done"
            op = task["ops"][task["i"]]
            result = effects.run(self, op, task)
            if result == "block":
                return "block"
            task.pop("ans", None)
            task["i"] += 1
            if result == "pushed" or self.phase != Phase.PLAYING:
                # Se resuelven primero los disparos apilados por esta operación.
                return "again" if task["i"] < len(task["ops"]) else "done"
        return "done"

    # ------------------------------------------------------------------ victoria
    def _leaders(self, sids: list[str]) -> list[str]:
        if not sids:
            return []
        best = max(self.pig_count(s) for s in sids)
        return [s for s in sids if self.pig_count(s) == best]

    def _check_win(self) -> bool:
        reached = [s for s in self.order if self.pig_count(s) >= self.goal]
        if not reached:
            return False
        self._finish("goal", self._leaders(reached))
        return True

    def _finish(self, reason: str, winners: list[str]) -> None:
        self.phase = Phase.FINISHED
        self.paused = False
        self.end_reason = reason
        self.winners = winners
        self.pending = []
        self.window = None
        self.work = []
        names = " y ".join(self.seats[w].name for w in winners if w in self.seats)
        if names:
            self.say(f"🏆 ¡{names} {'gana' if len(winners) == 1 else 'ganan'} la partida!")
        self.emit("game_finished", winners=[self.seats[w].name for w in winners if w in self.seats], reason=reason)
        self._changed()

    # ------------------------------------------------------------------ tiempo
    def next_deadline(self) -> float | None:
        if self.paused or self.phase != Phase.PLAYING:
            return None
        times = [d.deadline for d in self.pending if d.deadline is not None and not d.answered]
        if self.window is not None and self.window.deadline is not None:
            times.append(self.window.deadline)
        return min(times) if times else None

    def tick(self) -> bool:
        """Aplica vencimientos (ventana de réplica, ausentes). True si cambió el estado."""
        if self.paused or self.phase != Phase.PLAYING:
            return False
        now = self.now()
        changed = False
        for _ in range(50):
            w = self.window
            if w is not None and w.deadline is not None and now >= w.deadline:
                self._close_window()
                self._run()
                changed = True
                continue
            due = [d for d in self.pending if not d.answered and d.deadline is not None and now >= d.deadline]
            if not due:
                break
            for d in due:
                self.say(f"{self.seats[d.seat].name} no responde: se juega por defecto.")
                self._answer(d, self._default_answer(d))
            self._changed()
            self._after_answer()
            changed = True
        return changed

    # ------------------------------------------------------------------ comprobaciones
    def check_invariants(self) -> None:
        """Lanza AssertionError si el estado es incoherente (usado en tests y simulación)."""
        zones: list[list[str]] = [self.deck, self.discard, self.nursery, self.limbo]
        for s in self.seats.values():
            zones += [s.hand, s.pen]
        seen: list[str] = [u for z in zones for u in z]
        if self.phase == Phase.PLAYING or self.phase == Phase.FINISHED:
            removed = set(self.cards) - set(seen)
            # Las cartas de jugadores expulsados van a El Monte: nunca desaparecen.
            assert not removed, f"cartas perdidas: {sorted(removed)[:5]}"
        assert len(seen) == len(set(seen)), "carta en dos zonas"
        for s in self.seats.values():
            for uid in s.pen:
                assert self.card(uid).kind not in ("trick", "neigh", "super_neigh"), "carta imposible en pocilga"
            for uid in s.hand:
                assert self.card(uid).kind != "baby", "lechón en la mano"
        if self.phase == Phase.PLAYING:
            assert self.work or self.pending or self.window, "partida sin nada que hacer"
            seats = {d.seat for d in self.pending if not d.answered}
            assert seats <= set(self.seats), "decisión de jugador inexistente"

    # ------------------------------------------------------------------ vistas
    def card_view(self, uid: str) -> dict[str, Any]:
        data = self.card(uid).public()
        data["uid"] = uid
        return data

    def _seat_public(self, s: Seat) -> dict[str, Any]:
        return {
            "id": s.id,
            "name": s.name,
            "avatar": s.avatar,
            "connected": s.connected,
            "hand_count": len(s.hand),
            "pigs": self.pig_count(s.id) if self.phase != Phase.LOBBY else 0,
            "pen": [self.card_view(u) for u in s.pen],
            "hand_limit": self.hand_limit(s.id) if self.phase != Phase.LOBBY else BASE_HAND_LIMIT,
            "no_react": not self.can_react(s.id) if self.phase != Phase.LOBBY else False,
        }

    def _decision_view(self, d: Decision, private: bool) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": d.id,
            "seat": d.seat,
            "kind": d.kind,
            "prompt": d.prompt,
            "answered": d.answered,
            "remaining_ms": None
            if d.deadline is None
            else int(max(0.0, d.deadline - (self._paused_at if self.paused and self._paused_at else self.now())) * 1000),
        }
        if d.source:
            data["source"] = self.card_view(d.source)
        if private:
            data["min"] = d.min
            data["max"] = d.max
            if d.kind == "player":
                data["options"] = [{"id": o, "name": self.seats[o].name, "avatar": self.seats[o].avatar} for o in d.options]
            elif d.kind in ("cards", "discard"):
                opts = []
                for uid in d.options:
                    item = self.card_view(uid)
                    owner = self.owner_of(uid)
                    item["owner"] = owner
                    item["owner_name"] = self.seats[owner].name if owner else None
                    opts.append(item)
                data["options"] = opts
        return data

    def _window_view(self) -> dict[str, Any] | None:
        w = self.window
        if w is None:
            return None
        now = self._paused_at if self.paused and self._paused_at else self.now()
        return {
            "id": w.id,
            "card": self.card_view(w.card),
            "actor": w.actor,
            "last": w.last,
            "chain": [self.card_view(u) for u in w.chain],
            "passed": list(w.passed),
            "waiting": [s for s in self.eligible_reactors() if s not in w.passed],
            "remaining_ms": None if w.deadline is None else int(max(0.0, w.deadline - now) * 1000),
            "duration_ms": int(w.duration * 1000),
            "cancels": len(w.chain) % 2 == 1,
        }

    def view(self, role: str, player_id: str | None = None) -> dict[str, Any]:
        """Estado visible para un rol: 'tv', 'host' o 'player'. Las manos solo van a su dueño."""
        seats = sorted(self.seats.values(), key=lambda s: self.order.index(s.id) if s.id in self.order else 100 + s.order)
        state: dict[str, Any] = {
            "type": "state",
            "version": self.version,
            "phase": self.phase.value,
            "paused": self.paused,
            "code": self.code,
            "settings": self.settings.as_dict(),
            "min_players": MIN_PLAYERS,
            "max_players": MAX_PLAYERS,
            "goal": self.goal or (self.settings.goal or auto_goal(max(len(self.seats), MIN_PLAYERS))),
            "players": [self._seat_public(s) for s in seats],
            "active": self.active,
            "turn": self.turn,
            "deck_count": len(self.deck),
            "nursery_count": len(self.nursery),
            "discard_count": len(self.discard),
            "discard_top": [self.card_view(u) for u in self.discard[-3:]],
            "in_play": [self.card_view(u) for u in self.limbo if self.window is None or u != self.window.card and u not in self.window.chain],
            "window": self._window_view(),
            "waiting_for": [self._decision_view(d, False) for d in self.pending if not d.answered],
            "log": self.log[-12:],
            "winners": list(self.winners),
            "end_reason": self.end_reason,
        }
        if role == "player" and player_id in self.seats:
            seat = self.seats[player_id]
            plays = self.legal_plays(player_id)
            mine = [d for d in self.pending if d.seat == player_id and not d.answered]
            you: dict[str, Any] = {
                "id": seat.id,
                "name": seat.name,
                "avatar": seat.avatar,
                "hand": [self.card_view(u) for u in seat.hand],
                "playable": {u: t for u, t in plays.items()},
                "decisions": [self._decision_view(d, True) for d in mine],
                "can_draw_instead": any(d.kind == "turn" for d in mine),
            }
            w = self.window
            if w is not None and player_id in self.eligible_reactors():
                you["react"] = {
                    "window_id": w.id,
                    "passed": player_id in w.passed,
                    "cards": [u for u in seat.hand if self.card(u).kind in NEIGH_KINDS] if self.can_react(player_id) else [],
                    "blocked": not self.can_react(player_id),
                }
            state["you"] = you
        return state

    def summary(self) -> dict[str, Any]:
        """Resumen compacto para eventos de Home Assistant."""
        return {
            "phase": self.phase.value,
            "code": self.code,
            "players": len(self.seats),
            "turn": self.turn,
            "active": self.seats[self.active].name if self.active in self.seats else None,
        }

    # ------------------------------------------------------------------ serialización
    def to_dict(self) -> dict[str, Any]:
        """Estado completo serializable en JSON (para persistir entre reinicios)."""
        now = self.now()
        st = self.rng.getstate()

        def rem(t: float | None) -> float | None:
            return None if t is None else max(0.0, t - now)

        return {
            "v": 1,
            "rng": [st[0], list(st[1]), st[2]],
            "settings": self.settings.as_dict(),
            "seats": [
                {**{k: getattr(s, k) for k in ("id", "name", "avatar", "order", "hand", "pen")}}
                for s in self.seats.values()
            ],
            "order": self.order,
            "join_counter": self._join_counter,
            "id_counter": self._id_counter,
            "code": self.code,
            "phase": self.phase.value,
            "paused": self.paused,
            "cards": self.cards,
            "deck": self.deck,
            "discard": self.discard,
            "nursery": self.nursery,
            "limbo": self.limbo,
            "work": self.work,
            "pending": [
                {**{k: getattr(d, k) for k in ("id", "seat", "kind", "prompt", "options", "min", "max", "source", "answer", "answered")}}
                for d in self.pending
            ],
            "window": None
            if self.window is None
            else {
                **{k: getattr(self.window, k) for k in ("id", "card", "actor", "last", "chain", "passed", "duration")},
                "remaining": rem(self.window.deadline),
            },
            "active": self.active,
            "turn": self.turn,
            "goal": self.goal,
            "winners": self.winners,
            "end_reason": self.end_reason,
            "log": self.log,
            "log_seq": self._log_seq,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], catalog: Catalog, clock: Callable[[], float]) -> Game:
        """Reconstruye una partida. Los jugadores empiezan desconectados hasta que vuelvan."""
        if data.get("v") != 1:
            raise ValueError("Versión de estado desconocida")
        rng = random.Random()
        game = cls(catalog, clock, rng=rng, settings=Settings(**data["settings"]))
        for c in set(data["cards"].values()):
            if c not in catalog.cards:
                raise ValueError(f"Carta desconocida en la partida guardada: {c}")
        game.seats = {
            s["id"]: Seat(s["id"], s["name"], s["avatar"], s["order"], False, list(s["hand"]), list(s["pen"]))
            for s in data["seats"]
        }
        game.order = list(data["order"])
        game._join_counter = data["join_counter"]
        game._id_counter = data["id_counter"]
        game.code = data["code"]
        game.phase = Phase(data["phase"])
        game.paused = data["paused"]
        game._paused_at = clock() if game.paused else None
        game.cards = dict(data["cards"])
        game.deck, game.discard = list(data["deck"]), list(data["discard"])
        game.nursery, game.limbo = list(data["nursery"]), list(data["limbo"])
        game.work = data["work"]
        game.pending = [Decision(**d) for d in data["pending"]]
        for d in game.pending:
            if not d.answered:
                d.deadline = game._absent_deadline()
        w = data["window"]
        if w is not None:
            rem = w.pop("remaining")
            game.window = Window(**w)
            game.window.deadline = None if game.paused else clock() + (rem if rem is not None else game.settings.react_seconds)
        game.active = data["active"]
        game.turn = data["turn"]
        game.goal = data["goal"]
        game.winners = list(data["winners"])
        game.end_reason = data["end_reason"]
        game.log = list(data["log"])
        game._log_seq = data["log_seq"]
        # Al final: el constructor ya ha consumido números aleatorios (código de sala).
        r = data["rng"]
        rng.setstate((r[0], tuple(r[1]), r[2]))
        if game.phase == Phase.PLAYING:
            game.check_invariants()
        return game
