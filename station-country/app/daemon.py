"""
Daemon pro stanoviště země.

Tok:
  1. Default screen → obrázek země čeká
  2. Čip přiložen
  3. Validace dat z čipu (magic + CRC)
  4. Pokud OK:
     a) Sestav uvítací větu + náhodný fakt
     b) Pošli na frontend (přes SSE)
     c) Zapiš aktualizovaná data na čip
  5. Frontend zobrazí na X sekund, pak zpět na default
  6. Pokud čip neplatný → ukaž chybovou hlášku
"""
import asyncio
import json
import logging
import random
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiohttp import web

# Přidat shared do path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from countries import get_country_by_index
from greeting import build_greeting_for_visit
from nfc_device import NfcDevice, MockNfcDevice, create_nfc_device
from passport_chip import CHIP_SIZE, PassportChip

from app.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("station-country")


# ==========================================================================
# Stav
# ==========================================================================

class StationState:
    """Sdílený stav stanice - připojení SSE klientů, poslední event."""

    def __init__(self) -> None:
        self.sse_clients: list[web.StreamResponse] = []
        self.last_event: Optional[dict] = None

    async def push(self, event_type: str, data: dict) -> None:
        payload = {"type": event_type, "data": data}
        self.last_event = payload
        message = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        alive = []
        for client in self.sse_clients:
            try:
                await client.write(message.encode("utf-8"))
                alive.append(client)
            except (ConnectionResetError, ConnectionError):
                pass
        self.sse_clients = alive


state = StationState()


# ==========================================================================
# Lokální audit log (pro post-event statistiky)
# ==========================================================================

def log_scan(uid_or_name: str, action: str, details: dict = None) -> None:
    """Lokální audit log - jen pro forenzní účely."""
    log_file = config.log_dir / "scans.jsonl"
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "country_idx": config.country_index,
        "tag": uid_or_name,
        "action": action,
    }
    if details:
        entry.update(details)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Audit log chyba: {e}")


# ==========================================================================
# Hlavní handler scanu
# ==========================================================================

async def handle_tag(nfc: NfcDevice, chip: Optional[PassportChip], raw_data: bytes) -> None:
    """Callback z NFC reader. chip=None znamená že čip není inicializovaný."""
    country = get_country_by_index(config.country_index)
    if country is None:
        logger.error(f"Invalid country index {config.country_index}")
        return

    # ---- Neznámý/neinicializovaný čip ----
    if chip is None:
        logger.info("Neznámý nebo prázdný čip")
        log_scan("unknown", "rejected_invalid_chip")
        await state.push("error", {
            "message": "Pas musí nejdříve projít registrací na imigračním oddělení. "
                       "Zajdi si prosím na registrační stanoviště.",
            "code": "not_registered",
        })
        return

    # ---- Validní pas - vygeneruj větu ----
    if not chip.is_registered:
        # Neprázdný čip ale bez jména - taky chyba
        logger.warning("Čip má validní strukturu ale prázdné jméno")
        await state.push("error", {
            "message": "Pas není správně zaregistrovaný. Zajdi na imigrační oddělení.",
            "code": "no_name",
        })
        return

    logger.info(f"Scan: {chip.first_name} (last_country={chip.last_country_idx})")

    try:
        greeting, is_completion = build_greeting_for_visit(chip, config.country_index)
    except Exception as e:
        logger.error(f"Greeting chyba: {e}")
        await state.push("error", {"message": "Chyba systému."})
        return

    # Náhodný fakt (jen pro běžnou návštěvu)
    fact = random.choice(country.facts) if country.facts and not is_completion else None

    # ---- Aktualizuj čip a zapiš ZPĚT ----
    chip.record_visit(config.country_index)
    new_data = chip.to_bytes()

    write_ok = await nfc.write_data(new_data)
    if not write_ok:
        logger.error("Zápis na čip selhal!")
        # I tak dáme uživateli pozitivní zážitek, jen log
        log_scan(chip.first_name, "write_failed")

    log_scan(
        chip.first_name,
        "completion" if is_completion else "visit",
        {
            "visits_now": chip.visits_to(config.country_index),
            "unique_countries": chip.unique_countries_visited,
            "write_ok": write_ok,
        },
    )

    # ---- Pošli na frontend ----
    if is_completion:
        await state.push("completion", {"greeting": greeting})
    else:
        await state.push("scan", {
            "greeting": greeting,
            "fact": fact,
            "country_name": country.name_cz,
            "visits": chip.visits_to(config.country_index),
        })


# ==========================================================================
# HTTP server (frontend + SSE)
# ==========================================================================

async def index_handler(request: web.Request) -> web.Response:
    return web.FileResponse(config.frontend_dir / "index.html")


async def events_handler(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
    await response.prepare(request)
    state.sse_clients.append(response)

    # Pošli init event
    country = get_country_by_index(config.country_index)
    init_payload = {
        "type": "init",
        "data": {
            "country_index": config.country_index,
            "country_name": country.name_cz if country else None,
            "country_code": country.code if country else None,
            "return_to_default_seconds": config.return_to_default_seconds,
            "completion_show_seconds": config.completion_show_seconds,
        },
    }
    msg = f"data: {json.dumps(init_payload, ensure_ascii=False)}\n\n"
    try:
        await response.write(msg.encode("utf-8"))
    except Exception:
        pass

    # Keepalive ping
    try:
        while True:
            await asyncio.sleep(15)
            try:
                await response.write(b": keepalive\n\n")
            except Exception:
                break
    finally:
        if response in state.sse_clients:
            state.sse_clients.remove(response)

    return response


async def mock_handler(request: web.Request) -> web.Response:
    """Dev endpoint - GET /mock?name=Pavel&gender=M&year=2014 vyrobí čip a 'přiloží'."""
    if not isinstance(request.app["nfc"], MockNfcDevice):
        return web.json_response({"error": "not in mock mode"}, status=400)

    action = request.query.get("action", "scan")

    if action == "blank":
        await request.app["nfc"].simulate_blank_tag()
        return web.json_response({"status": "blank chip simulated"})

    if action == "scan":
        name = request.query.get("name", "Test").strip()
        gender = request.query.get("gender", "M")
        year = int(request.query.get("year", "2014"))

        chip = PassportChip(first_name=name, gender=gender, birth_year=year)

        # Pokud chce uživatel nasimulovat předchozí návštěvy
        visits_str = request.query.get("visited", "")
        if visits_str:
            for idx_str in visits_str.split(","):
                idx_str = idx_str.strip()
                if idx_str:
                    chip.record_visit(int(idx_str))

        await request.app["nfc"].simulate_tag(chip.to_bytes())

        # Po simulaci dej do response stav čipu (jak by ho stanice po zápisu uložila)
        readback = await request.app["nfc"].read_data()
        readback_chip = PassportChip.from_bytes(readback) if readback else None
        return web.json_response({
            "status": "ok",
            "after": {
                "name": readback_chip.first_name if readback_chip else None,
                "last_country_idx": readback_chip.last_country_idx if readback_chip else None,
                "completed": readback_chip.completed if readback_chip else None,
                "unique_countries": readback_chip.unique_countries_visited if readback_chip else None,
                "visits_to_this": readback_chip.visits_to(config.country_index) if readback_chip else None,
            } if readback_chip else None,
        })

    return web.json_response({"error": "unknown action"}, status=400)


async def health_handler(request: web.Request) -> web.Response:
    country = get_country_by_index(config.country_index)
    return web.json_response({
        "status": "ok",
        "country_index": config.country_index,
        "country_name": country.name_cz if country else None,
        "nfc_device": config.nfc_device,
        "sse_clients": len(state.sse_clients),
    })


def create_app(nfc: NfcDevice) -> web.Application:
    app = web.Application()
    app["nfc"] = nfc
    app.router.add_get("/", index_handler)
    app.router.add_get("/events", events_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/mock", mock_handler)
    app.router.add_static("/css", config.frontend_dir / "css")
    app.router.add_static("/js", config.frontend_dir / "js")
    app.router.add_static("/assets", config.frontend_dir / "assets")
    return app


# ==========================================================================
# Main
# ==========================================================================

async def main() -> None:
    country = get_country_by_index(config.country_index)
    logger.info(f"== Stanice: {country.name_cz} (idx={config.country_index}) ==")
    logger.info(f"NFC device: {config.nfc_device}")
    logger.info(f"Kiosk port: {config.kiosk_port}")

    nfc = create_nfc_device(config.nfc_device, config.debounce_seconds)

    # Spusť NFC polling
    async def on_tag(chip, raw_data):
        await handle_tag(nfc, chip, raw_data)

    await nfc.start_polling(on_tag)

    # Spusť HTTP server
    app = create_app(nfc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.kiosk_port)
    await site.start()
    logger.info(f"HTTP běží na http://0.0.0.0:{config.kiosk_port}")

    # Wait for shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    logger.info("Shutting down...")
    await nfc.stop()
    await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
