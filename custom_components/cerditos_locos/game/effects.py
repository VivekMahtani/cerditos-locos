"""Operaciones de efecto de las cartas.

Cada operación del catálogo tiene aquí un manejador registrado con ``@op``. Un
manejador recibe la partida, la operación y la tarea ``ops`` en curso, y devuelve:

- ``"done"``: terminado.
- ``"pushed"``: terminado, pero ha apilado disparos que deben resolverse antes de
  seguir con la siguiente operación.
- ``"block"``: ha creado decisiones y espera respuesta. Cuando llegan, el motor
  vuelve a llamar al manejador con ``task["ans"]`` relleno.

Los objetivos se calculan siempre en el servidor y se revalidan al aplicar la
respuesta: si dejaron de ser válidos, la operación «se esfuma».
Para añadir una operación: un manejador aquí, su firma en ``catalog.OPS`` y tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .engine import Game

Handler = Callable[["Game", dict[str, Any], dict[str, Any]], str]
_HANDLERS: dict[str, Handler] = {}


def op(name: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[name] = fn
        return fn

    return deco


def registered() -> set[str]:
    return set(_HANDLERS)


def run(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    return _HANDLERS[operation["op"]](game, operation, task)


# ---------------------------------------------------------------------- objetivos
def target_options(game: Game, sid: str, spec: dict[str, Any], protect: str | None) -> list[str]:
    owners = {"self": [sid], "other": game.others(sid), "any": [sid, *game.others(sid)]}[spec["owner"]]
    result = []
    for owner in owners:
        if owner not in game.seats:
            continue
        for uid in game.seats[owner].pen:
            if game.card(uid).kind not in spec["kinds"]:
                continue
            if protect and game.is_protected(uid, protect):
                continue
            result.append(uid)
    return result


PROTECTION = {"scare": "scare", "steal_pig": "steal", "return_to_hand": None, "remove": None}


def _player_options(game: Game, sid: str, flt: str) -> list[str]:
    opts = game.others(sid)
    if flt == "other_with_hand":
        opts = [o for o in opts if game.seats[o].hand]
    return opts


def has_effect(game: Game, operation: dict[str, Any], sid: str) -> bool:
    """¿Tiene sentido ofrecer este efecto opcional ahora?"""
    name = operation["op"]
    if name in PROTECTION:
        return bool(target_options(game, sid, operation["target"], PROTECTION[name]))
    if name == "bring_baby":
        return bool(game.nursery)
    if name == "search_deck":
        return any(game.card(u).kind in operation["kinds"] for u in game.deck)
    if name == "choose_player":
        return bool(_player_options(game, sid, operation["filter"]))
    return True


def _answer(task: dict[str, Any]) -> Any:
    ans = task.get("ans") or {}
    return next(iter(ans.values())) if ans else None


def _owner_name(game: Game, uid: str) -> str:
    owner = game.owner_of(uid)
    return game.seats[owner].name if owner else "nadie"


# ---------------------------------------------------------------------- operaciones
@op("draw")
def _draw(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    if game.draw(sid, operation["n"]):
        game.say(f"{game.seats[sid].name} roba {operation['n']} carta(s).")
    return "done"


@op("discard")
def _discard(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    ctx = task["ctx"]
    if task.get("ans"):
        waiting: dict[str, str] = ctx.pop("await", {})
        for did, chosen in task["ans"].items():
            who = waiting.get(did)
            if who not in game.seats:
                continue
            moved = [u for u in chosen if u in game.seats[who].hand]
            for u in moved:
                game._move(u, game.discard)
            if moved:
                names = ", ".join(game.cname(u) for u in moved)
                game.say(f"{game.seats[who].name} descarta {names}.")
        return "done"
    who = operation["who"]
    seats = {"self": [sid], "others": game.others(sid), "all": [sid, *game.others(sid)]}[who]
    waiting = {}
    for s in seats:
        hand = game.seats[s].hand
        n = min(operation["n"], len(hand))
        if n == 0:
            continue
        src = game.cname(task["src"])
        did = game.ask(s, "discard", f"{src}: descarta {n} carta(s).", list(hand), n, n, source=task["src"])
        waiting[did] = s
    if not waiting:
        return "done"
    ctx["await"] = waiting
    return "block"


def _targeted(game: Game, operation: dict[str, Any], task: dict[str, Any], prompt: str) -> str | None:
    """Devuelve el uid elegido, ``"block"`` si hay que preguntar, o None si no hay objetivo."""
    sid = task["seat"]
    protect = PROTECTION[operation["op"]]
    options = target_options(game, sid, operation["target"], protect)
    chosen = _answer(task)
    if chosen is not None:
        uid = chosen[0] if chosen else None
        return uid if uid in options else None
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    game.ask(sid, "cards", prompt, options, 1, 1, source=task["src"])
    return "block"


def _fizzle(game: Game, task: dict[str, Any]) -> str:
    game.say(f"{game.cname(task['src'])} no encuentra a quién afectar.")
    return "done"


@op("scare")
def _scare(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    uid = _targeted(game, operation, task, "Elige el cerdo que se va a espantar.")
    if uid == "block":
        return "block"
    if uid is None:
        return _fizzle(game, task)
    owner = _owner_name(game, uid)
    baby = game.card(uid).kind == "baby"
    game._leave_pen(uid)
    where = "vuelve al corral" if baby else "se escapa al monte"
    game.say(f"¡{game.cname(uid)} de {owner} {where}!")
    game.emit("pig_scared", card=game.cards[uid], owner=owner)
    return "done"


@op("steal_pig")
def _steal_pig(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    uid = _targeted(game, operation, task, "Elige el cerdo que te llevas.")
    if uid == "block":
        return "block"
    if uid is None:
        return _fizzle(game, task)
    owner = _owner_name(game, uid)
    before = len(game.work)
    game.enter_pen(uid, sid)
    game.say(f"{game.seats[sid].name} se lleva {game.cname(uid)} de la pocilga de {owner}.")
    game.emit("pig_stolen", card=game.cards[uid], to=sid)
    return "pushed" if len(game.work) > before else "done"


@op("return_to_hand")
def _return_to_hand(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    uid = _targeted(game, operation, task, "Elige el cerdo que vuelve a la mano de su dueño.")
    if uid == "block":
        return "block"
    if uid is None:
        return _fizzle(game, task)
    owner = game.owner_of(uid)
    assert owner is not None
    if game.card(uid).kind == "baby":
        game._leave_pen(uid)
        game.say(f"{game.cname(uid)} de {game.seats[owner].name} vuelve al corral.")
    else:
        game._move(uid, game.seats[owner].hand)
        game.say(f"{game.cname(uid)} vuelve a la mano de {game.seats[owner].name}.")
    return "done"


@op("remove")
def _remove(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    uid = _targeted(game, operation, task, "Elige el chollo o fastidio que se retira.")
    if uid == "block":
        return "block"
    if uid is None:
        return _fizzle(game, task)
    owner = _owner_name(game, uid)
    game._leave_pen(uid)
    game.say(f"{game.cname(uid)} sale de la pocilga de {owner}.")
    return "done"


@op("bring_baby")
def _bring_baby(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    if not game.nursery:
        game.say("No quedan lechones en el corral.")
        return "done"
    uid = game.nursery[-1]
    before = len(game.work)
    game.enter_pen(uid, sid)
    game.say(f"Un lechón llega a la pocilga de {game.seats[sid].name}.")
    return "pushed" if len(game.work) > before else "done"


@op("search_deck")
def _search_deck(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    options = [u for u in game.deck if game.card(u).kind in operation["kinds"]]
    chosen = _answer(task)
    if chosen is None:
        if not options:
            game.say(f"{game.seats[sid].name} busca en el mazo, pero no encuentra nada.")
            return "done"
        # Una opción por tipo de carta: no importa qué copia concreta se elija.
        unique: dict[str, str] = {}
        for u in options:
            unique.setdefault(game.cards[u], u)
        game.ask(sid, "cards", "Elige la carta que te llevas del mazo.", list(unique.values()), 1, 1, source=task["src"])
        return "block"
    uid = chosen[0] if chosen else None
    if uid in options:
        game._move(uid, game.seats[sid].hand)
        game.say(f"{game.seats[sid].name} busca en el mazo y se lleva una carta.")
    game.rng.shuffle(game.deck)
    return "done"


@op("choose_player")
def _choose_player(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    options = _player_options(game, sid, operation["filter"])
    chosen = _answer(task)
    if chosen is None:
        if not options:
            task["ctx"]["abort"] = True
            return _fizzle(game, task)
        if len(options) == 1:
            task["ctx"]["player"] = options[0]
            return "done"
        game.ask(sid, "player", "Elige a un rival.", options, 1, 1, source=task["src"])
        return "block"
    if chosen not in options:
        task["ctx"]["abort"] = True
        return _fizzle(game, task)
    task["ctx"]["player"] = chosen
    return "done"


@op("take_random_hand")
def _take_random_hand(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    victim = task["ctx"].get("player")
    if victim not in game.seats or not game.seats[victim].hand:
        return "done"
    uid = game.rng.choice(game.seats[victim].hand)
    game._move(uid, game.seats[sid].hand)
    game.say(f"{game.seats[sid].name} se queda una carta de la mano de {game.seats[victim].name}.")
    return "done"


@op("give_card")
def _give_card(game: Game, operation: dict[str, Any], task: dict[str, Any]) -> str:
    sid = task["seat"]
    victim = task["ctx"].get("player")
    hand = game.seats[sid].hand
    if victim not in game.seats or not hand:
        return "done"
    chosen = _answer(task)
    if chosen is None:
        game.ask(sid, "cards", f"Elige la carta que le das a {game.seats[victim].name}.", list(hand), 1, 1, source=task["src"])
        return "block"
    uid = chosen[0] if chosen else None
    if uid not in hand:
        uid = game.rng.choice(hand)
    game._move(uid, game.seats[victim].hand)
    game.say(f"{game.seats[sid].name} le da una carta a {game.seats[victim].name}.")
    return "done"
