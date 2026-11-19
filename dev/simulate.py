"""Simulación masiva de partidas con bots para detectar bloqueos y medir el equilibrio.

    python3 dev/simulate.py --games 10000
    python3 dev/simulate.py --games 2000 --players 4 --chaos

Cada partida usa una semilla distinta y comprueba las invariantes del motor tras
cada acción. ``--chaos`` añade desconexiones, reconexiones, caducidad de ventanas y
expulsiones al azar. Termina con código 1 si alguna partida falla.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "cerditos_locos"
sys.path.insert(0, str(INTEGRATION))

from game.bots import bot_step  # noqa: E402
from game.catalog import load_catalog  # noqa: E402
from game.engine import Game, Phase, Settings  # noqa: E402


def run_one(catalog, seed: int, players: int, chaos: bool, check: bool) -> Game:
    t = [0.0]
    g = Game(catalog, lambda: t[0], rng=random.Random(seed), settings=Settings())
    for i in range(players):
        g.add_player(f"Bot{i}")
    g.start()
    rng = random.Random(seed * 31 + 7)
    steps = 0
    while g.phase == Phase.PLAYING:
        steps += 1
        if steps > 20000:
            raise AssertionError("la partida no termina")
        r = rng.random() if chaos else 1.0
        if r < 0.04:
            sid = rng.choice(g.order)
            g.set_connected(sid, not g.seats[sid].connected)
        elif r < 0.045 and len(g.order) > 2:
            g.remove_player(rng.choice(g.order))
        elif r < 0.2 or not bot_step(g, rng):
            t[0] += rng.choice([1, 5, 31]) if chaos else 9
            if not g.tick() and not chaos:
                raise AssertionError("partida bloqueada")
        if check:
            g.check_invariants()
    return g


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--players", type=int, default=0, help="0 = repartir entre 2 y 6")
    parser.add_argument("--chaos", action="store_true")
    parser.add_argument("--no-check", action="store_true", help="no comprobar invariantes (más rápido)")
    args = parser.parse_args()

    catalog = load_catalog(INTEGRATION / "data" / "cards_es.json")
    turns: dict[int, list[int]] = defaultdict(list)
    reasons: Counter[str] = Counter()
    seat_wins: dict[int, Counter[int]] = defaultdict(Counter)
    failures = 0
    start = time.time()
    for seed in range(args.games):
        players = args.players or 2 + seed % 5
        try:
            g = run_one(catalog, seed, players, args.chaos, not args.no_check)
        except Exception:  # noqa: BLE001 - se informa y se sigue
            failures += 1
            print(f"✗ semilla {seed} ({players} jugadores):", file=sys.stderr)
            traceback.print_exc()
            continue
        turns[players].append(g.turn)
        reasons[g.end_reason or "?"] += 1
        if not args.chaos:
            for w in g.winners:
                seat_wins[players][g.order.index(w)] += 1

    elapsed = time.time() - start
    print(f"{args.games} partidas en {elapsed:.1f} s · fallos: {failures}")
    print(f"Final: {dict(reasons)}")
    print("Jugadores · turnos (media / mediana / máx) · rondas medias · victorias por puesto de salida")
    for n in sorted(turns):
        ts = turns[n]
        wins = seat_wins[n]
        total = sum(wins.values()) or 1
        dist = " ".join(f"{100 * wins[k] / total:4.1f}%" for k in range(n)) if wins else "-"
        print(
            f"  {n} · {statistics.mean(ts):5.1f} / {statistics.median(ts):4.0f} / {max(ts):3d}"
            f" · {statistics.mean(ts) / n:4.1f} · {dist}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
