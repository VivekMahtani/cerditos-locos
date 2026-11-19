"""Pruebas del motor: reglas, efectos, réplicas, ausencias, victoria y vistas."""

from __future__ import annotations

import json
import random

import pytest

from conftest import make_game
from game import effects
from game.bots import play_out
from game.catalog import OPS, CatalogError, parse_card, parse_catalog
from game.engine import MAX_PLAYERS, Game, GameError, Phase, Settings, auto_goal


# ---------------------------------------------------------------- utilidades
def take(g: Game, sid: str, cid: str) -> str:
    """Pone en la mano de ``sid`` una copia de ``cid`` sacada del mazo o de El Monte."""
    for zone in (g.deck, g.discard):
        for uid in zone:
            if g.cards[uid] == cid:
                g._move(uid, g.seats[sid].hand)
                return uid
    for s in g.seats.values():  # último recurso: de otra mano
        for uid in s.hand:
            if g.cards[uid] == cid and s.id != sid:
                g._move(uid, g.seats[sid].hand)
                return uid
    raise AssertionError(f"no queda ninguna {cid}")


def to_pen(g: Game, sid: str, cid: str) -> str:
    uid = take(g, sid, cid)
    g._move(uid, g.seats[sid].pen)
    return uid


def pass_all(g: Game) -> None:
    """Todos dejan pasar la ventana de réplica abierta."""
    while g.window is not None:
        w = g.window
        waiting = [s for s in g.eligible_reactors() if s not in w.passed]
        assert waiting
        g.react(waiting[0], w.id, None)


def turn_of(g: Game) -> str:
    d = next(d for d in g.pending if d.kind == "turn")
    return d.seat


def decision(g: Game, sid: str | None = None):
    return next(d for d in g.pending if not d.answered and (sid is None or d.seat == sid))


def finish_turn(g: Game) -> None:
    """Termina el turno actual robando y descartando lo que haga falta."""
    sid = turn_of(g)
    g.draw_instead(sid)
    while g.pending and g.pending[0].kind == "discard" and g.pending[0].seat == sid:
        d = g.pending[0]
        g.decide(sid, d.id, d.options[: d.min])


# ---------------------------------------------------------------- catálogo
def test_builtin_catalog(catalog):
    assert catalog.warnings == []
    assert catalog.deck_size() == 70
    assert catalog.deck_size(include_neighs=False) == 60
    assert set(OPS) == effects.registered()
    kinds = {c.kind for c in catalog.cards.values()}
    assert kinds == {"baby", "pig", "magic_pig", "trick", "perk", "pest", "neigh", "super_neigh"}
    for c in catalog.cards.values():
        assert len(c.text) <= 140


@pytest.mark.parametrize(
    "card",
    [
        {"id": "x", "name": "X", "type": "pig", "copies": 1, "text": "t"},  # id corto
        {"id": "xx", "name": "X", "type": "dragon", "copies": 1, "text": "t"},
        {"id": "xx", "name": "X", "type": "pig", "copies": 0, "text": "t"},
        {"id": "xx", "name": "X", "type": "pig", "copies": 1, "text": ""},
        {"id": "xx", "name": "X", "type": "trick", "copies": 1, "text": "t", "triggers": [{"when": "enter", "do": [{"op": "draw", "n": 1}]}]},
        {"id": "xx", "name": "X", "type": "trick", "copies": 1, "text": "t", "triggers": [{"when": "play", "do": [{"op": "hack"}]}]},
        {"id": "xx", "name": "X", "type": "trick", "copies": 1, "text": "t", "triggers": [{"when": "play", "do": [{"op": "draw", "n": 9}]}]},
        {"id": "xx", "name": "X", "type": "trick", "copies": 1, "text": "t", "triggers": [{"when": "play", "do": [{"op": "scare", "target": {"owner": "x", "kinds": ["pig"]}}]}]},
        {"id": "xx", "name": "X", "type": "trick", "copies": 1, "text": "t", "triggers": [{"when": "play", "do": [{"op": "take_random_hand"}]}]},
        {"id": "xx", "name": "X", "type": "magic_pig", "copies": 1, "text": "t", "static": [{"mod": "fly"}]},
        {"id": "xx", "name": "X", "type": "pig", "copies": 1, "text": "t", "static": [{"mod": "no_react"}]},
        {"id": "xx", "name": "X", "type": "pig", "copies": 1, "text": "t", "code": "import os"},
    ],
)
def test_catalog_rejects_bad_cards(card):
    with pytest.raises(CatalogError):
        parse_card(card)


def test_catalog_drops_invalid_and_duplicates():
    data = {
        "cards": [
            {"id": "bebe", "name": "B", "type": "baby", "copies": 2, "text": "t"},
            {"id": "cerdo", "name": "C", "type": "pig", "copies": 2, "text": "t"},
            {"id": "cerdo", "name": "C2", "type": "pig", "copies": 2, "text": "t"},
            {"id": "malo", "name": "M", "type": "pig", "copies": 99, "text": "t"},
        ]
    }
    cat = parse_catalog(data)
    assert set(cat.cards) == {"bebe", "cerdo"}
    assert len(cat.warnings) == 2
    with pytest.raises(CatalogError):
        parse_catalog({"cards": [{"id": "cerdo", "name": "C", "type": "pig", "copies": 2, "text": "t"}]})


# ---------------------------------------------------------------- sala y reparto
def test_lobby_rules(catalog, clock):
    g = Game(catalog, clock, rng=random.Random(1))
    g.add_player("Ana")
    with pytest.raises(GameError) as e:
        g.add_player("ána")
    assert e.value.code == "name_taken"
    with pytest.raises(GameError) as e:
        g.start()
    assert e.value.code == "not_enough_players"
    for i in range(MAX_PLAYERS - 1):
        g.add_player(f"P{i}")
    with pytest.raises(GameError) as e:
        g.add_player("Otro")
    assert e.value.code == "room_full"


def test_start_deals_and_no_late_join(catalog, clock):
    g = make_game(catalog, clock, players=4)
    assert g.phase == Phase.PLAYING
    assert g.goal == auto_goal(4) == 6
    for sid in g.order:
        s = g.seats[sid]
        assert len(s.pen) == 1 and g.card(s.pen[0]).kind == "baby"
        assert len(s.hand) == (6 if sid == g.active else 5)  # el primero ya ha robado
    assert len(g.deck) == 70 - 4 * 5 - 1
    assert turn_of(g) == g.active
    with pytest.raises(GameError) as e:
        g.add_player("Tarde")
    assert e.value.code == "game_running"
    g.check_invariants()


def test_goal_depends_on_players(catalog, clock):
    assert make_game(catalog, clock, players=5).goal == 5
    assert make_game(catalog, clock, players=2, goal=4).goal == 4


def test_disconnected_lobby_players_are_left_out(catalog, clock):
    g = Game(catalog, clock, rng=random.Random(3))
    a, b, c = (g.add_player(n) for n in ("A", "B", "C"))
    g.set_connected(c.id, False)
    g.start()
    assert set(g.order) == {a.id, b.id}


# ---------------------------------------------------------------- turno
def test_turn_cycle_draw_instead(game):
    first = turn_of(game)
    hand = len(game.seats[first].hand)
    game.draw_instead(first)
    assert len(game.seats[first].hand) == hand + 1
    second = turn_of(game)
    assert second == game.order[1] and game.turn == 1
    assert len(game.seats[second].hand) == 6


def test_actions_out_of_turn_rejected(game):
    other = game.order[1]
    uid = game.seats[other].hand[0]
    with pytest.raises(GameError) as e:
        game.play(other, uid)
    assert e.value.code == "not_your_turn"
    with pytest.raises(GameError):
        game.draw_instead(other)
    me = turn_of(game)
    with pytest.raises(GameError) as e:
        game.play(me, uid)
    assert e.value.code == "not_in_hand"


def test_neigh_not_playable_in_action(game):
    me = turn_of(game)
    uid = take(game, me, "ni_hablar")
    assert uid not in game.legal_plays(me)
    with pytest.raises(GameError) as e:
        game.play(me, uid)
    assert e.value.code == "not_playable"


def test_hand_limit_discard_at_end(game):
    me = turn_of(game)
    for _ in range(3):
        take(game, me, "cerdo_rosado")
    assert len(game.seats[me].hand) == 9
    game.draw_instead(me)  # 10 cartas, límite 7
    d = decision(game, me)
    assert d.kind == "discard" and d.min == d.max == 3
    with pytest.raises(GameError):
        game.decide(me, d.id, d.options[:2])
    game.decide(me, d.id, d.options[:3])
    assert len(game.seats[me].hand) == 7
    assert turn_of(game) != me


def test_comedero_raises_limit_and_charca_draws_more(game):
    me = turn_of(game)
    to_pen(game, me, "comedero")
    to_pen(game, me, "charca")
    assert game.hand_limit(me) == 9
    assert game.draw_amount(me) == 2
    while len(game.seats[me].hand) < 8:
        take(game, me, "cerdo_rosado")
    game.draw_instead(me)  # 9 cartas: sin descarte
    assert turn_of(game) != me
    # vuelta completa hasta que le toca otra vez: roba 2
    while turn_of(game) != me:
        finish_turn(game)
    assert len(game.seats[me].hand) == 9 + 2


# ---------------------------------------------------------------- jugar y réplicas
def test_play_pig_with_reaction_window(game):
    me = turn_of(game)
    uid = take(game, me, "cerdo_rosado")
    game.play(me, uid)
    assert game.window is not None and uid in game.limbo
    assert set(game.eligible_reactors()) == set(game.order) - {me}
    view = game.view("player", game.order[1])
    assert view["you"]["react"]["window_id"] == game.window.id
    assert "react" not in game.view("player", me)["you"]
    pass_all(game)
    assert uid in game.seats[me].pen
    assert game.pig_count(me) == 2


def test_window_closes_by_timeout(game, clock):
    me = turn_of(game)
    uid = take(game, me, "cerdo_rosado")
    game.play(me, uid)
    clock.advance(7.9)
    assert not game.tick()
    clock.advance(0.2)
    assert game.tick()
    assert game.window is None and uid in game.seats[me].pen


def test_neigh_cancels_and_counter_neigh(game):
    me, b, c = game.order
    pig = take(game, me, "cerdo_rosado")
    n1 = take(game, b, "ni_hablar")
    n2 = take(game, me, "ni_hablar")
    game.play(me, pig)
    game.react(b, game.window.id, n1)
    assert game.window.last == b and game.window.chain == [n1]
    assert set(game.eligible_reactors()) == {me, c}
    game.react(me, game.window.id, n2)  # contrarréplica: la carta vuelve a valer
    pass_all(game)
    assert pig in game.seats[me].pen
    assert n1 in game.discard and n2 in game.discard


def test_neigh_cancels_card(game):
    me, b, _ = game.order
    pig = take(game, me, "cerdo_rosado")
    n1 = take(game, b, "ni_hablar")
    game.play(me, pig)
    game.react(b, game.window.id, n1)
    pass_all(game)
    assert pig in game.discard and game.pig_count(me) == 1
    assert turn_of(game) != me


def test_super_neigh_closes_window(game):
    me, b, _ = game.order
    pig = take(game, me, "cerdo_rosado")
    sn = take(game, b, "ni_hablar_punto")
    game.play(me, pig)
    game.react(b, game.window.id, sn)
    assert game.window is None
    assert pig in game.discard


def test_stale_window_and_double_pass(game):
    me, b, _ = game.order
    pig = take(game, me, "cerdo_rosado")
    game.play(me, pig)
    wid = game.window.id
    game.react(b, wid, None)
    game.react(b, wid, None)  # repetir «dejar pasar» no rompe nada
    assert game.window is not None
    pass_all(game)
    with pytest.raises(GameError) as e:
        game.react(b, wid, None)
    assert e.value.code == "stale_window"


def test_flies_block_reactions(game):
    me, b, _ = game.order
    to_pen(game, b, "nube_moscas")
    n1 = take(game, b, "ni_hablar")
    pig = take(game, me, "cerdo_rosado")
    game.play(me, pig)
    react = game.view("player", b)["you"]["react"]
    assert react["blocked"] and react["cards"] == []
    with pytest.raises(GameError):
        game.react(b, game.window.id, n1)


def test_reactions_disabled(catalog, clock):
    g = make_game(catalog, clock, react_seconds=0)
    assert not any(g.card(u).kind in ("neigh", "super_neigh") for u in g.cards)
    me = turn_of(g)
    g.play(me, take(g, me, "cerdo_rosado"))
    assert g.window is None and g.pig_count(me) == 2


def test_pest_needs_target(game):
    me, b, _ = game.order
    pest = take(game, me, "valla_rota")
    assert set(game.legal_plays(me)[pest]) == {b, game.order[2]}
    with pytest.raises(GameError) as e:
        game.play(me, pest)
    assert e.value.code == "bad_target"
    game.play(me, pest, b)
    pass_all(game)
    assert pest in game.seats[b].pen


def test_sticky_mud_blocks_tricks(game):
    me = turn_of(game)
    to_pen(game, me, "barro_pegajoso")
    trick = take(game, me, "siesta")
    assert trick not in game.legal_plays(me)


# ---------------------------------------------------------------- efectos
def test_gloton_draws_on_enter(game):
    me = turn_of(game)
    uid = take(game, me, "cerdo_gloton")
    hand = len(game.seats[me].hand)
    game.play(me, uid)
    pass_all(game)
    assert len(game.seats[me].hand) == hand - 1 + 1


def test_jabali_optional_scare_and_guardian(game):
    me, b, c = game.order
    guardian = to_pen(game, b, "cerdo_guardian")
    b_baby = game.seats[b].pen[0]
    c_baby = game.seats[c].pen[0]
    jab = take(game, me, "jabali_grunon")
    game.play(me, jab)
    pass_all(game)
    d = decision(game, me)
    assert d.kind == "yes_no"
    game.decide(me, d.id, True)
    d = decision(game, me)
    assert d.kind == "cards"
    # El lechón de B está protegido por el Guardián; el Guardián mismo no.
    assert b_baby not in d.options and guardian in d.options and c_baby in d.options
    game.decide(me, d.id, [c_baby])
    assert c_baby in game.nursery  # los lechones vuelven al corral
    assert game.pig_count(c) == 0


def test_jabali_declined(game):
    me = turn_of(game)
    jab = take(game, me, "jabali_grunon")
    game.play(me, jab)
    pass_all(game)
    d = decision(game, me)
    game.decide(me, d.id, False)
    assert turn_of(game) != me
    assert all(game.pig_count(s) == 1 for s in game.order if s != me)


def test_optional_without_targets_is_not_asked(game):
    me, b, c = game.order
    for s in (b, c):
        g_baby = game.seats[s].pen[0]
        game._leave_pen(g_baby)
    jab = take(game, me, "jabali_grunon")
    game.play(me, jab)
    pass_all(game)
    assert turn_of(game) != me  # nada que espantar: ni siquiera pregunta


def test_stale_decision_rejected(game):
    me, b, _ = game.order
    jab = take(game, me, "jabali_grunon")
    game.play(me, jab)
    pass_all(game)
    d = decision(game, me)
    with pytest.raises(GameError) as e:
        game.decide(b, d.id, True)
    assert e.value.code == "not_yours"
    game.decide(me, d.id, False)
    with pytest.raises(GameError) as e:
        game.decide(me, d.id, True)
    assert e.value.code == "stale_decision"


def test_fence_blocks_steal_and_open_gate_steals(game):
    me, b, c = game.order
    pig_b = to_pen(game, b, "cerdo_manchado")
    to_pen(game, b, "valla_nueva")
    pig_c = to_pen(game, c, "cerdo_rizado")
    trick = take(game, me, "cerca_abierta")
    game.play(me, trick)
    pass_all(game)
    # Solo hay un objetivo válido (el de C): se aplica sin preguntar.
    assert pig_c in game.seats[me].pen and pig_b in game.seats[b].pen
    assert trick in game.discard


def test_mud_bath_returns_to_hand(game):
    me, b, _ = game.order
    pig = to_pen(game, b, "cerdo_manchado")
    trick = take(game, me, "bano_de_barro")
    game.play(me, trick)
    pass_all(game)
    d = decision(game, me)
    game.decide(me, d.id, [pig])
    assert pig in game.seats[b].hand


def test_drummer_parallel_discards(game):
    me, b, c = game.order
    drum = take(game, me, "cerdo_tamborilero")
    game.play(me, drum)
    pass_all(game)
    ds = [d for d in game.pending if d.kind == "discard"]
    assert {d.seat for d in ds} == {b, c}
    hb, hc = len(game.seats[b].hand), len(game.seats[c].hand)
    game.decide(b, ds[0].id if ds[0].seat == b else ds[1].id, [game.seats[b].hand[0]])
    assert game.pending  # espera al otro jugador
    dc = next(d for d in game.pending if d.seat == c)
    game.decide(c, dc.id, [game.seats[c].hand[-1]])
    assert turn_of(game) == b  # B es el siguiente: descartó 1 y ya ha robado 1
    assert len(game.seats[b].hand) == hb and len(game.seats[c].hand) == hc - 1


def test_truffle_search(game):
    me = turn_of(game)
    pig = take(game, me, "cerdo_trufero")
    tricks_in_deck = {game.cards[u] for u in game.deck if game.card(u).kind == "trick"}
    game.play(me, pig)
    pass_all(game)
    d = decision(game, me)
    assert {game.cards[u] for u in d.options} == tricks_in_deck  # una opción por tipo
    choice = d.options[0]
    game.decide(me, d.id, [choice])
    assert choice in game.seats[me].hand


def test_market_take_and_give(game):
    me, b, c = game.order
    trick = take(game, me, "mercadillo")
    game.play(me, trick)
    pass_all(game)
    d = decision(game, me)
    assert d.kind == "player" and set(d.options) == {b, c}
    hc = len(game.seats[c].hand)
    hm = len(game.seats[me].hand)
    game.decide(me, d.id, c)
    d = decision(game, me)
    assert d.kind == "cards" and len(game.seats[me].hand) == hm + 1
    game.decide(me, d.id, [d.options[0]])
    assert len(game.seats[c].hand) == hc
    game.check_invariants()


def test_broken_fence_discards_at_turn_start(game):
    me, b, _ = game.order
    to_pen(game, b, "valla_rota")
    finish_turn(game)  # pasa a B: primero descarta
    d = decision(game, b)
    assert d.kind == "discard" and d.min == 1
    hand = len(game.seats[b].hand)
    game.decide(b, d.id, [game.seats[b].hand[0]])
    assert len(game.seats[b].hand) == hand - 1 + 1  # descarta y luego roba


def test_midwife_brings_baby(game):
    me, b, _ = game.order
    to_pen(game, b, "cerda_comadrona")
    finish_turn(game)
    d = decision(game, b)
    assert d.kind == "yes_no"
    game.decide(b, d.id, True)
    assert game.pig_count(b) == 3  # lechón inicial + comadrona + lechón nuevo


def test_sleepy_counts_double_and_wins(game):
    me = turn_of(game)
    for cid in ("cerdo_rosado", "cerdo_manchado", "cerdo_rizado"):
        to_pen(game, me, cid)
    assert game.pig_count(me) == 4
    sleepy = take(game, me, "cerdo_dormilon")
    game.play(me, sleepy)
    pass_all(game)
    assert game.pig_count(me) == 6
    assert game.phase == Phase.FINISHED and game.winners == [me] and game.end_reason == "goal"
    with pytest.raises(GameError):
        game.draw_instead(turn_of(game) if game.pending else me)


def test_deck_runs_out(game):
    me = turn_of(game)
    to_pen(game, game.order[1], "cerdo_rosado")
    while game.deck:
        game._move(game.deck[-1], game.discard)
    game.draw_instead(me)
    assert game.phase == Phase.FINISHED and game.end_reason == "deck"
    assert game.winners == [game.order[1]]


def test_target_removed_fizzles(game):
    """Un objetivo que desaparece entre la elección y la resolución se esfuma."""
    me, b, c = game.order
    jab = take(game, me, "jabali_grunon")
    game.play(me, jab)
    pass_all(game)
    game.decide(me, decision(game, me).id, True)
    d = decision(game, me)
    target = d.options[0]
    game._leave_pen(target)  # desaparece por otra vía
    with pytest.raises(GameError):
        game.decide(me, d.id, ["inexistente"])
    game.decide(me, d.id, [target])
    assert any("no encuentra" in e["text"] for e in game.log)
    game.check_invariants()


# ---------------------------------------------------------------- ausencias, pausa, anfitrión
def test_absent_player_defaults_after_timeout(game, clock):
    me = turn_of(game)
    game.set_connected(me, False)
    clock.advance(29)
    assert not game.tick()
    clock.advance(2)
    assert game.tick()
    assert turn_of(game) != me
    assert any("no responde" in e["text"] for e in game.log)


def test_disconnected_player_not_waited_in_window(game):
    me, b, c = game.order
    pig = take(game, me, "cerdo_rosado")
    game.play(me, pig)
    game.set_connected(c, False)
    game.react(b, game.window.id, None)
    assert game.window is None and pig in game.seats[me].pen


def test_pause_freezes_timers(game, clock):
    me = turn_of(game)
    game.play(me, take(game, me, "cerdo_rosado"))
    game.pause()
    with pytest.raises(GameError):
        game.react(game.order[1], game.window.id, None)
    clock.advance(100)
    assert not game.tick()
    game.resume()
    clock.advance(7)
    assert not game.tick()
    clock.advance(2)
    assert game.tick() and game.window is None


def test_host_skip(game):
    me = turn_of(game)
    game.skip()
    assert turn_of(game) != me
    me2 = turn_of(game)
    game.play(me2, take(game, me2, "cerdo_rosado"))
    game.skip()  # cierra la ventana de réplica
    assert game.window is None


def test_remove_active_player(game):
    me, b, c = game.order
    game.play(me, take(game, me, "cerdo_rosado"))
    game.remove_player(me)
    assert me not in game.seats and game.window is None
    assert turn_of(game) == b
    game.check_invariants()
    game.remove_player(c)
    assert game.phase == Phase.FINISHED and game.winners == [b]


def test_remove_waiting_player(game):
    me, b, c = game.order
    game.play(me, take(game, me, "cerdo_tamborilero"))
    pass_all(game)
    game.remove_player(b)
    dc = decision(game, c)
    game.decide(c, dc.id, dc.options[:1])
    assert turn_of(game) == c
    game.check_invariants()


def test_new_game_resets(game):
    game.end()
    assert game.phase == Phase.FINISHED
    code = game.code
    game.new_game()
    assert game.phase == Phase.LOBBY and game.code != code and len(game.seats) == 3
    assert all(not s.hand and not s.pen for s in game.seats.values())
    game.start()
    game.check_invariants()


def test_configure_limits(catalog, clock):
    g = Game(catalog, clock, rng=random.Random(1))
    g.configure({"goal": 99, "react_seconds": 2, "absent_seconds": 1})
    assert g.settings.as_dict() == {"goal": 8, "react_seconds": 4, "absent_seconds": 10}
    g.configure({"goal": 1})
    assert g.settings.goal == 3
    with pytest.raises(GameError):
        g.configure({"goal": "7"})


# ---------------------------------------------------------------- vistas y privacidad
def _hand_uids(g: Game) -> dict[str, set[str]]:
    return {sid: set(s.hand) for sid, s in g.seats.items()}


def test_hands_never_leak(game):
    rng = random.Random(5)
    from game.bots import bot_step

    for _ in range(200):
        if game.phase != Phase.PLAYING:
            break
        hands = _hand_uids(game)
        for role in ("tv", "host"):
            text = json.dumps(game.view(role))
            for uids in hands.values():
                assert not any(f'"{u}"' in text for u in uids if u not in json.dumps(game.view(role)["players"]))
        for sid in game.order:
            text = json.dumps(game.view("player", sid))
            for other, uids in hands.items():
                if other != sid:
                    # Las cartas ajenas solo pueden aparecer si son públicas (pocilga, ventana, en juego).
                    assert not any(f'"uid": "{u}"' in text for u in uids), "mano ajena filtrada"
        bot_step(game, rng)


def test_player_view_has_what_to_play(game):
    me = turn_of(game)
    you = game.view("player", me)["you"]
    assert you["can_draw_instead"] and you["decisions"][0]["kind"] == "turn"
    assert set(you["playable"]) <= {c["uid"] for c in you["hand"]}
    other = game.view("player", game.order[1])["you"]
    assert other["playable"] == {} and not other["can_draw_instead"]
    tv = game.view("tv")
    assert "you" not in tv and tv["waiting_for"][0]["seat"] == me
    assert "options" not in tv["waiting_for"][0]


# ---------------------------------------------------------------- serialización
def test_serialization_roundtrip(catalog, clock):
    g = make_game(catalog, clock, players=4, seed=9)
    rng = random.Random(9)
    from game.bots import bot_step

    for _ in range(60):
        bot_step(g, rng)
    data = json.loads(json.dumps(g.to_dict()))
    g2 = Game.from_dict(data, catalog, clock)
    v1, v2 = g.view("tv"), g2.view("tv")
    for k in ("players", "active", "turn", "deck_count", "discard_count", "log", "phase", "goal"):
        if k == "players":
            for a, b in zip(v1[k], v2[k], strict=True):
                assert {**a, "connected": None} == {**b, "connected": None}
        else:
            assert v1[k] == v2[k]
    assert all(not s.connected for s in g2.seats.values())
    for sid in g2.order:
        g2.set_connected(sid, True)
    # Mismas semillas, misma continuación.
    play_out(g2, random.Random(1))
    assert g2.phase == Phase.FINISHED


def test_restore_rejects_unknown_cards(catalog, clock, game):
    data = game.to_dict()
    data["cards"]["c1"] = "carta_inventada"
    with pytest.raises(ValueError):
        Game.from_dict(data, catalog, clock)


# ---------------------------------------------------------------- simulación
@pytest.mark.parametrize("players", [2, 3, 4, 5, 6])
def test_simulated_games_finish(catalog, players):
    for seed in range(40):
        clock = [0.0]
        g = Game(catalog, lambda: clock[0], rng=random.Random(seed), settings=Settings())
        for i in range(players):
            g.add_player(f"B{i}")
        g.start()
        play_out(g, random.Random(seed + 1000))
        assert g.winners and g.end_reason in ("goal", "deck")


def test_simulated_with_disconnections_and_timeouts(catalog):
    """Jugadores que se van y vuelven, ventanas que caducan: nunca se bloquea."""
    from game.bots import bot_step

    for seed in range(60):
        t = [0.0]
        g = Game(catalog, lambda: t[0], rng=random.Random(seed), settings=Settings(react_seconds=5))
        for i in range(4):
            g.add_player(f"B{i}")
        g.start()
        rng = random.Random(seed)
        steps = 0
        while g.phase == Phase.PLAYING:
            steps += 1
            assert steps < 20000
            r = rng.random()
            if r < 0.05:
                sid = rng.choice(g.order)
                g.set_connected(sid, not g.seats[sid].connected)
            elif r < 0.25 or not bot_step(g, rng):
                t[0] += rng.choice([1, 5, 31])
                g.tick()
            g.check_invariants()
            if rng.random() < 0.002 and len(g.order) > 2:
                g.remove_player(rng.choice(g.order))
                g.check_invariants()
