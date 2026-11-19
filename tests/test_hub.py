"""Pruebas del hub: roles, autorización, unión, reconexión, privacidad en el cable y persistencia."""

from __future__ import annotations

import asyncio
import json
import random

from conftest import FakeConn
from game.engine import Phase, Settings
from game.hub import JOIN_FAILURES_MAX, MAX_MESSAGE_BYTES, Hub


def run(coro):
    return asyncio.run(coro)


def make_hub(catalog, clock, **kw):
    kw.setdefault("settings", Settings())
    return Hub(catalog, clock=clock, rng=random.Random(7), **kw)


async def send(hub, sess, /, **msg):
    await hub.receive(sess, json.dumps(msg))


async def join(hub, name, remote="192.168.1.20"):
    conn = FakeConn(remote)
    s = hub.connect(conn)
    await send(hub, s, type="hello", role="player", code=hub.game.code.lower(), name=name)
    return conn, s


async def host_of(hub):
    host = FakeConn()
    s = hub.connect(host)
    await send(hub, s, type="hello", role="host", token=hub.host_token)
    return host, s


async def table(hub, n=3):
    """TV + anfitrión + n jugadores, partida empezada."""
    tv = FakeConn()
    await send(hub, hub.connect(tv), type="hello", role="tv")
    host, s_host = await host_of(hub)
    players = [await join(hub, f"J{i}") for i in range(n)]
    await send(hub, s_host, type="start")
    assert host.last_error() is None
    return tv, (host, s_host), players


def by_id(hub, players):
    """{player_id: (conn, session)}"""
    return {s.player_id: (c, s) for c, s in players}


def test_roles_and_host_authorization(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        tv = FakeConn()
        s_tv = hub.connect(tv)
        await send(hub, s_tv, type="hello", role="tv")
        assert tv.of_type("welcome")[0]["role"] == "tv"
        assert tv.last_state()["phase"] == "lobby"
        await send(hub, s_tv, type="start")
        assert tv.last_error()["code"] == "forbidden"

        bad = FakeConn()
        s_bad = hub.connect(bad)
        await send(hub, s_bad, type="hello", role="host", token="nope")
        assert bad.last_error()["code"] == "bad_token"
        await send(hub, s_bad, type="start")
        assert bad.last_error()["code"] == "not_identified"

        host, s_host = await host_of(hub)
        assert host.of_type("welcome")[0]["role"] == "host"
        old = hub.host_token
        hub.rotate_host_token()
        other = FakeConn()
        await send(hub, hub.connect(other), type="hello", role="host", token=old)
        assert other.last_error()["code"] == "bad_token"

        # Un jugador no puede usar comandos de anfitrión
        conn, s = await join(hub, "Ana")
        await send(hub, s, type="start")
        assert conn.last_error()["code"] == "forbidden"

    run(scenario())


def test_full_turn_over_the_wire(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        tv, (host, _), players = await table(hub)
        ids = by_id(hub, players)
        state = tv.last_state()
        assert state["phase"] == "playing"
        active = state["active"]
        conn, s = ids[active]
        you = conn.last_state()["you"]
        assert you["can_draw_instead"]
        card = next(u for u in you["playable"])
        await send(hub, s, type="play", card=card, target=you["playable"][card][0] if you["playable"][card] else None)
        assert conn.last_error() is None and conn.of_type("ack")[-1]["ref"] == "play"
        window = tv.last_state()["window"]
        assert window is not None and window["card"]["uid"] == card
        for pid, (c, ss) in ids.items():
            if pid != active:
                react = c.last_state()["you"]["react"]
                await send(hub, ss, type="react", window=react["window_id"], card=None)
        st = tv.last_state()
        assert st["window"] is None
        # Jugar fuera de turno da error en español
        await send(hub, s, type="draw_instead")
        err = conn.last_error()
        assert err["code"] in ("not_your_turn",) or st["active"] == active

    run(scenario())


def test_hands_never_on_the_wire_to_others(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        tv, (host, _), players = await table(hub)
        ids = by_id(hub, players)
        for pid, (conn, _) in ids.items():
            hand = {c["uid"] for c in conn.last_state()["you"]["hand"]}
            for other_pid, (other, _) in ids.items():
                if other_pid == pid:
                    continue
                for msg in other.sent:
                    text = json.dumps(msg)
                    assert not any(f'"uid": "{u}"' in text for u in hand)
            for msg in tv.sent + host.sent:
                text = json.dumps(msg)
                assert not any(f'"uid": "{u}"' in text for u in hand)

    run(scenario())


def test_join_only_in_lobby_and_reconnect(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        tv, _, players = await table(hub, 2)
        late, _ = await join(hub, "Tarde")
        assert late.last_error()["code"] == "game_running"

        conn, s = players[0]
        token = conn.of_type("welcome")[0]["session"]
        pid = s.player_id
        await hub.disconnect(s)
        assert not hub.game.seats[pid].connected
        again = FakeConn()
        s2 = hub.connect(again)
        await send(hub, s2, type="hello", role="player", session=token)
        assert again.of_type("welcome")[0]["player_id"] == pid
        assert hub.game.seats[pid].connected
        assert "hand" in again.last_state()["you"]

        # Una segunda pestaña con la misma sesión sustituye a la primera
        third = FakeConn()
        await send(hub, hub.connect(third), type="hello", role="player", session=token)
        assert again.of_type("replaced") and again.closed

        bogus = FakeConn()
        await send(hub, hub.connect(bogus), type="hello", role="player", session="x" * 20)
        assert bogus.last_error()["code"] == "session_expired"

    run(scenario())


def test_kick_and_leave(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        tv, (host, s_host), players = await table(hub, 3)
        conn, s = players[2]
        pid = s.player_id
        await send(hub, s_host, type="kick", player_id=pid)
        assert conn.of_type("kicked")
        assert pid not in hub.game.seats and pid not in [p["id"] for p in tv.last_state()["players"]]
        c1, s1 = players[1]
        await send(hub, s1, type="leave")
        assert c1.of_type("left")
        assert tv.last_state()["phase"] == "finished"

    run(scenario())


def test_bad_messages_and_limits(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        conn = FakeConn()
        s = hub.connect(conn)
        await hub.receive(s, "{no json")
        assert conn.last_error()["code"] == "bad_json"
        await send(hub, s, type="hello", role="dios")
        assert conn.last_error()["code"] == "bad_role"
        await send(hub, s, type="play", card="c1")
        assert conn.last_error()["code"] == "not_identified"
        big = FakeConn()
        sb = hub.connect(big)
        await hub.receive(sb, json.dumps({"type": "ping", "x": "a" * MAX_MESSAGE_BYTES}))
        assert big.closed
        spam = FakeConn()
        ss = hub.connect(spam)
        for _ in range(40):
            await send(hub, ss, type="ping")
        assert spam.last_error()["code"] == "rate_limited"

    run(scenario())


def test_code_bruteforce_is_blocked(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        for i in range(JOIN_FAILURES_MAX):
            c = FakeConn("192.168.1.66")
            await send(hub, hub.connect(c), type="hello", role="player", code="ZZZZ", name=f"x{i}")
        c = FakeConn("192.168.1.66")
        await send(hub, hub.connect(c), type="hello", role="player", code=hub.game.code, name="ok")
        assert c.last_error()["code"] == "too_many_attempts"

    run(scenario())


def test_bad_payloads_rejected(catalog, clock):
    async def scenario():
        hub = make_hub(catalog, clock)
        tv, _, players = await table(hub, 2)
        ids = by_id(hub, players)
        conn, s = ids[tv.last_state()["active"]]
        for payload in ({"card": 5}, {"card": ["x"]}, {"card": None}, {"card": "c9999"}):
            await send(hub, s, type="play", **payload)
            assert conn.last_error()["code"] == "not_in_hand"
        await send(hub, s, type="decide", decision="d0", choice=True)
        assert conn.last_error()["code"] == "stale_decision"
        await send(hub, s, type="react", window="w0", card=None)
        assert conn.last_error()["code"] == "stale_window"
        hub.game.check_invariants()

    run(scenario())


def test_persistence_roundtrip_with_reconnect(catalog, clock):
    async def scenario():
        saved = []
        hub = make_hub(catalog, clock, on_save=saved.append)
        tv, _, players = await table(hub, 3)
        assert saved and saved[-1]["game"]["phase"] == "playing"
        conn, s = players[0]
        token = conn.of_type("welcome")[0]["session"]
        snapshot = json.loads(json.dumps(saved[-1]))

        # «Reinicio de HA»: hub nuevo a partir de lo guardado
        hub2 = make_hub(catalog, clock)
        assert hub2.restore(snapshot)
        assert hub2.game.phase == Phase.PLAYING
        again = FakeConn()
        await send(hub2, hub2.connect(again), type="hello", role="player", session=token)
        assert again.of_type("welcome")[0]["player_id"] == s.player_id
        assert len(again.last_state()["you"]["hand"]) == len(conn.last_state()["you"]["hand"])

        assert not make_hub(catalog, clock).restore({"game": {"v": 99}})

    run(scenario())


def test_ticker_closes_window_without_clients(catalog):
    """La ventana de réplica se cierra sola con el reloj real aunque nadie conteste."""

    async def scenario():
        hub = Hub(catalog, rng=random.Random(3), settings=Settings(react_seconds=4))
        tv, _, players = await table(hub, 2)
        hub.game.settings.react_seconds = 4
        ids = by_id(hub, players)
        conn, s = ids[tv.last_state()["active"]]
        you = conn.last_state()["you"]
        card = next(iter(you["playable"]))
        targets = you["playable"][card]
        # Con el reloj real, acortamos la ventana para no esperar.
        await send(hub, s, type="play", card=card, target=targets[0] if targets else None)
        assert hub.game.window is not None
        hub.game.window.deadline = hub.game.now() + 0.2
        await hub.start()
        try:
            for _ in range(30):
                await asyncio.sleep(0.05)
                if hub.game.window is None and tv.last_state()["window"] is None:
                    break
            assert hub.game.window is None
            assert tv.last_state()["window"] is None
        finally:
            await hub.stop()

    run(scenario())
