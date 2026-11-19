"""Prueba de extremo a extremo con navegadores reales (Playwright + Chrome).

Requiere el servidor de desarrollo en marcha:
    python3 dev/devserver.py --port 8765 --goal 4
y después:
    python3 tests/e2e/run_e2e.py --base http://127.0.0.1:8765 --out /tmp/shots

Simula una TV (1920x1080), el panel de anfitrión y 3 móviles que juegan una partida
completa tocando la interfaz (jugar cartas, elegir objetivos, replicar, decidir),
incluida la recarga de un móvil a mitad de partida. Comprueba que ninguna mano
llega a la TV y falla si hay errores de consola.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path

from playwright.async_api import async_playwright

PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}
NAMES = ["Ana", "Beto", "Carla"]


async def visible(page, selector: str) -> bool:
    loc = page.locator(selector)
    return await loc.count() > 0 and await loc.first.is_visible()


async def act(page, rng: random.Random, shots: dict, out: Path, name: str) -> str | None:
    """Hace una acción en el móvil si tiene algo que hacer. Devuelve qué hizo."""
    if await visible(page, ".panel.hot >> text=Dejar pasar"):
        if "react" not in shots:
            shots["react"] = True
            await page.screenshot(path=out / "08-movil-replica.png")
        neigh = page.locator(".panel.hot .btn.warn")
        if await neigh.count() and rng.random() < 0.35:
            await neigh.first.click()
            return "replica"
        await page.click(".panel.hot >> text=Dejar pasar")
        return "pasa"
    if await visible(page, ".panel.hot .btn.ok"):  # sí / no
        await page.click(".panel.hot .btn.ok")
        return "sí"
    if await visible(page, ".panel.hot .choice-player"):
        if "player" not in shots:
            shots["player"] = True
            await page.screenshot(path=out / "09-movil-elige-rival.png")
        await page.locator(".panel.hot .choice-player").first.click()
        await page.click(".panel.hot .btn.primary")
        return "elige rival"
    if await visible(page, ".panel.hot .hand .card"):
        if "cards" not in shots:
            shots["cards"] = True
            await page.screenshot(path=out / "10-movil-elige-carta.png")
        label = await page.locator(".panel.hot .btn-row .btn").first.text_content()
        need = 1
        if "(" in label:
            need = int(label.split("/")[-1].rstrip(")"))
        cards = page.locator(".panel.hot .hand .card")
        for i in range(min(need, await cards.count())):
            await cards.nth(i).click()
        await page.locator(".panel.hot .btn-row .btn").first.click()
        return "elige cartas"
    if await visible(page, "text=Robar en lugar de jugar"):
        playable = page.locator(".hand .card.playable")
        if await playable.count() and rng.random() < 0.85:
            await playable.nth(rng.randrange(await playable.count())).click()
            await page.wait_for_selector(".sheet")
            if "sheet" not in shots:
                await asyncio.sleep(0.4)
                shots["sheet"] = True
                await page.screenshot(path=out / "07-movil-carta.png")
            if await visible(page, ".sheet .choice-player"):
                await page.locator(".sheet .choice-player").first.click()
            await page.click(".sheet .btn.primary")
            return "juega"
        if "turn" not in shots:
            shots["turn"] = True
            await page.screenshot(path=out / "06-movil-turno.png")
        await page.click("text=Robar en lugar de jugar")
        return "roba"
    return None


async def main(base: str, out: Path, chrome: str | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    def watch(page, label):
        page.on("console", lambda m: errors.append(f"[{label}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[{label}] {e}"))

    tv_frames: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chrome) if chrome else await p.chromium.launch()
        tv_ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        tv = await tv_ctx.new_page()
        watch(tv, "tv")
        tv.on("websocket", lambda ws: ws.on("framereceived", lambda payload: tv_frames.append(payload if isinstance(payload, str) else "")))
        await tv.goto(f"{base}/cerditos_locos/tv")
        await tv.wait_for_selector(".join-card .room b")
        code = (await tv.text_content(".join-card .room b")).strip()
        assert len(code) == 4, code
        assert await tv.evaluate("() => { const i = document.querySelector('.join-card img'); return i.complete && i.naturalWidth > 0; }"), "QR sin cargar"

        host_ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        host = await host_ctx.new_page()
        watch(host, "host")
        await host.goto(f"{base}/dev/host")
        await host.wait_for_selector("cerditos-locos-panel >> text=Sala de espera")

        phones = []
        for i, name in enumerate(NAMES):
            ctx = await browser.new_context(**PHONE)
            page = await ctx.new_page()
            watch(page, name)
            url = f"{base}/cerditos_locos/play?code={code}" if i == 0 else f"{base}/cerditos_locos/play"
            await page.goto(url)
            await page.wait_for_selector("#name")
            if i > 0:
                await page.fill("#code", code.lower())
            await page.fill("#name", name)
            await page.click(f".avatars button >> nth={i * 2}")
            if i == 0:
                await page.screenshot(path=out / "02-movil-unirse.png")
            await page.click("button[type=submit]")
            await page.wait_for_selector("text=¡Ya estás en la pocilga!")
            phones.append(page)

        dup_ctx = await browser.new_context(**PHONE)
        dup = await dup_ctx.new_page()
        watch(dup, "dup")
        await dup.goto(f"{base}/cerditos_locos/play?code={code}")
        await dup.fill("#name", "ANA")
        await dup.click("button[type=submit]")
        await dup.wait_for_selector("text=Ese nombre ya está en uso")
        await dup_ctx.close()

        await tv.wait_for_selector(".seat-chip >> nth=2")
        await tv.screenshot(path=out / "01-tv-sala.png")
        await phones[0].screenshot(path=out / "03-movil-sala.png")
        await host.screenshot(path=out / "04-anfitrion-sala.png", full_page=True)

        await host.click("cerditos-locos-panel >> text=Empezar partida")
        await tv.wait_for_selector(".pens")
        await asyncio.sleep(0.5)
        await tv.screenshot(path=out / "05-tv-partida.png")

        rng = random.Random(11)
        shots: dict = {}
        actions = 0
        reloaded = False
        for _ in range(900):
            if await visible(tv, ".final"):
                break
            did = None
            for page in rng.sample(phones, len(phones)):
                did = await act(page, rng, shots, out, "")
                if did:
                    actions += 1
                    break
            if did == "juega" and "tv_window" not in shots and await visible(tv, "text=¿Alguien replica?"):
                shots["tv_window"] = True
                await tv.screenshot(path=out / "11-tv-replica.png")
            if actions == 12 and not reloaded:
                reloaded = True
                await phones[1].reload()
                await phones[1].wait_for_selector(".play-top .me")
            if actions == 20 and "host_live" not in shots:
                shots["host_live"] = True
                await host.screenshot(path=out / "12-anfitrion-partida.png", full_page=True)
                await tv.screenshot(path=out / "13-tv-avanzada.png")
            await asyncio.sleep(0.12 if did else 0.3)
        else:
            raise AssertionError("La partida no terminó")

        await tv.wait_for_selector(".final")
        await asyncio.sleep(1.2)
        await tv.screenshot(path=out / "14-tv-final.png")
        await phones[0].screenshot(path=out / "15-movil-final.png", full_page=True)
        print(f"Partida completa con {actions} acciones de móvil · capturas: {sorted(shots)}")

        # Privacidad: la TV nunca recibe cartas de una mano.
        for frame in tv_frames:
            try:
                msg = json.loads(frame)
            except ValueError:
                continue
            assert "you" not in msg and "hand" not in json.dumps(msg.get("players", [])).replace("hand_count", "").replace("hand_limit", ""), "mano filtrada a la TV"
        print(f"{len(tv_frames)} mensajes de la TV revisados: sin manos.")
        await browser.close()

    if errors:
        print("Errores de consola:")
        for e in errors:
            print("  ", e)
        raise SystemExit(1)
    print("Sin errores de consola.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--out", default="/tmp/shots")
    parser.add_argument("--chrome", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.base, Path(args.out), args.chrome))
