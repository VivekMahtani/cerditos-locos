"""Jugadores automáticos para pruebas y simulación (no se usan en partidas reales).

Eligen al azar entre acciones legales usando solo lo que vería su móvil
(``Game.view('player', id)``), así que también sirven para comprobar que la vista
privada contiene lo necesario para jugar.
"""

from __future__ import annotations

import random
from typing import Any

from .engine import Game, Phase


def bot_step(game: Game, rng: random.Random, react_chance: float = 0.3) -> bool:
    """Ejecuta una acción de algún bot. Devuelve False si no había nada que hacer."""
    if game.phase != Phase.PLAYING:
        return False
    # Réplicas primero: cualquiera que pueda contestar a la ventana abierta.
    if game.window is not None:
        reactors = [s for s in game.eligible_reactors() if s not in game.window.passed]
        if reactors:
            sid = rng.choice(reactors)
            you = game.view("player", sid)["you"]
            react = you.get("react")
            assert react is not None, "la vista no ofrece la réplica"
            card = rng.choice(react["cards"]) if react["cards"] and rng.random() < react_chance else None
            game.react(sid, react["window_id"], card)
            return True
        return False
    open_ = [d for d in game.pending if not d.answered]
    if not open_:
        return False
    d = rng.choice(open_)
    you = game.view("player", d.seat)["you"]
    dv = next(x for x in you["decisions"] if x["id"] == d.id)
    if dv["kind"] == "turn":
        playable: dict[str, Any] = you["playable"]
        if playable and rng.random() < 0.85:
            uid = rng.choice(sorted(playable))
            targets = playable[uid]
            game.play(d.seat, uid, rng.choice(targets) if targets else None)
        else:
            game.draw_instead(d.seat)
    elif dv["kind"] == "yes_no":
        game.decide(d.seat, d.id, rng.random() < 0.8)
    elif dv["kind"] == "player":
        game.decide(d.seat, d.id, rng.choice(dv["options"])["id"])
    else:
        n = rng.randint(dv["min"], dv["max"])
        ids = [o["uid"] for o in dv["options"]]
        game.decide(d.seat, d.id, rng.sample(ids, n))
    return True


def play_out(game: Game, rng: random.Random, max_steps: int = 5000, check: bool = True) -> int:
    """Juega hasta el final. Devuelve el número de acciones; lanza si se bloquea."""
    steps = 0
    while game.phase == Phase.PLAYING:
        if not bot_step(game, rng):
            raise AssertionError("Partida bloqueada: nadie puede actuar")
        if check:
            game.check_invariants()
        steps += 1
        if steps > max_steps:
            raise AssertionError("La partida no termina")
    return steps
