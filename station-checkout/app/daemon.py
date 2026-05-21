"""
Pokladna - kontrolní stanoviště.

Pouze čte čip a vyhodnocuje:
  - Validní registrovaný pas → ZELENÁ + jméno + pípnutí
  - Neplatný/prázdný čip → ČERVENÁ + bzučák

NEZAPISUJE nic na čip. Pokladna je read-only.
"""
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiohttp import web

# Path setup
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from nfc_device import NfcDevice, MockNfcDevice, create_nfc_device  # noqa: E402
from passport_chip import PassportChip, is_blank_chip  # noqa: E402
from countries import COUNTRIES, get_country_by_index  # noqa: E402

from app.config import config  # noqa: E402
from app.gpio_controller import GpioController, create_gpio  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("station-checkout")


# ==========================================================================
# Stav
# ==========================================================================

class CheckoutState:
    def __init__(self) -> None:
        self.sse_clients: list[web.StreamResponse] = []

    async def push(self, event_type: str, data: dict) -> None:
        payload = {"type": event_type, "data": data}
        message = f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
        alive = []
        for client in self.sse_clients:
            try:
                await client.write(message.encode("utf-8"))
                alive.append(client)
            except Exception:
                pass
        self.sse_clients = alive


state = CheckoutState()


# ==========================================================================
# Audit log
# ==========================================================================

def log_checkout(action: str, details: dict = None) -> None:
    log_file = config.log_dir / "checkouts.jsonl"
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "checkpoint": config.checkpoint_label,
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
# NFC handler
# ==========================================================================

async def handle_tag(
    gpio: GpioController,
    chip: Optional[PassportChip],
    raw_data: bytes,
) -> None:
    """Hlavní logika - vyhodnotí čip a reaguje vizuálně/akusticky."""

    # --- Neplatný čip (cizí karta, poškozená data) ---
    if chip is None:
        is_blank = is_blank_chip(raw_data)
        if is_blank:
            logger.warning("🔴 BLANK ČIP - neregistrovaný")
            message = "Pas není zaregistrovaný. Pošlete cestovatele na registraci."
            reason = "blank"
        else:
            logger.warning("🔴 NEPLATNÝ ČIP - cizí nebo poškozený")
            message = "Tento čip nepatří k naší akci."
            reason = "invalid"

        log_checkout("deny", {"reason": reason})

        await state.push("deny", {
            "reason": reason,
            "message": message,
        })

        # Paralelně: červená LED + bzučák
        await asyncio.gather(
            gpio.red_on(config.show_result_seconds),
            gpio.beep_fail(),
        )
        return

    # --- Validní pas ---
    if not chip.is_registered:
        # Validní struktura ale prázdné jméno - chyba registrace
        logger.warning(f"🔴 VALIDNÍ ČIP ale bez jména")
        log_checkout("deny", {"reason": "no_name"})
        await state.push("deny", {
            "reason": "no_name",
            "message": "Pas nemá vyplněné jméno. Vrať se na registraci.",
        })
        await asyncio.gather(
            gpio.red_on(config.show_result_seconds),
            gpio.beep_fail(),
        )
        return

    # --- OK - registrovaný a validní ---
    last_country_name = None
    if chip.last_country_idx < len(COUNTRIES):
        country = get_country_by_index(chip.last_country_idx)
        if country:
            last_country_name = country.name_cz

    logger.info(
        f"🟢 PŘIJATO: {chip.first_name} ({chip.gender}, {chip.birth_year}) - "
        f"{chip.unique_countries_visited}/{len(COUNTRIES)} zemí, "
        f"completed={chip.completed}"
    )

    log_checkout("accept", {
        "name": chip.first_name,
        "gender": chip.gender,
        "birth_year": chip.birth_year,
        "unique_countries": chip.unique_countries_visited,
        "completed": chip.completed,
    })

    await state.push("accept", {
        "passport": {
            "first_name": chip.first_name,
            "gender": chip.gender,
            "birth_year": chip.birth_year,
            "unique_countries": chip.unique_countries_visited,
            "total_countries": len(COUNTRIES),
            "completed": chip.completed,
            "last_country": last_country_name,
            "total_scans": chip.total_scans,
        },
    })

    # Paralelně: zelená LED + krátké pípnutí
    await asyncio.gather(
        gpio.green_on(config.show_result_seconds),
        gpio.beep_ok(),
    )


# ==========================================================================
# HTTP handlery
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

    # Init event
    init_payload = {
        "type": "init",
        "data": {
            "checkpoint_label": config.checkpoint_label,
            "show_result_seconds": config.show_result_seconds,
            "total_countries": len(COUNTRIES),
        },
    }
    try:
        msg = f"data: {json.dumps(init_payload, ensure_ascii=False)}\n\n"
        await response.write(msg.encode("utf-8"))
    except Exception:
        pass

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


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "checkpoint": config.checkpoint_label,
        "nfc_device": config.nfc_device,
        "gpio_enabled": config.gpio_enabled,
        "sse_clients": len(state.sse_clients),
    })


async def mock_handler(request: web.Request) -> web.Response:
    """Dev endpoint - simulace přiložení čipu."""
    nfc = request.app["nfc"]
    if not isinstance(nfc, MockNfcDevice):
        return web.json_response({"error": "Not in mock mode"}, status=400)

    action = request.query.get("action", "registered")

    if action == "registered":
        name = request.query.get("name", "Pavel")
        gender = request.query.get("gender", "M")
        year = int(request.query.get("year", "2014"))
        chip = PassportChip(first_name=name, gender=gender, birth_year=year)
        visited = request.query.get("visited", "")
        if visited:
            for idx_str in visited.split(","):
                if idx_str.strip():
                    chip.record_visit(int(idx_str))
        await nfc.simulate_tag(chip.to_bytes())
        return web.json_response({"status": "registered tag simulated", "name": name})

    if action == "complete":
        # Pas s dokončenou cestou (všech 11 zemí)
        name = request.query.get("name", "Žofie")
        gender = request.query.get("gender", "F")
        chip = PassportChip(first_name=name, gender=gender, birth_year=2014)
        for i in range(len(COUNTRIES)):
            chip.record_visit(i)
        await nfc.simulate_tag(chip.to_bytes())
        return web.json_response({"status": "completed passport simulated"})

    if action == "blank":
        await nfc.simulate_blank_tag()
        return web.json_response({"status": "blank tag simulated"})

    if action == "invalid":
        await nfc.simulate_tag(b"\xAA" * 64)
        return web.json_response({"status": "invalid tag simulated"})

    return web.json_response({"error": "Unknown action"}, status=400)


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
    logger.info(f"== Pokladna: {config.checkpoint_label} ==")
    logger.info(f"NFC device: {config.nfc_device}")
    logger.info(f"GPIO enabled: {config.gpio_enabled}")
    logger.info(f"HTTP port: {config.http_port}")

    # GPIO
    gpio = create_gpio(
        config.gpio_enabled,
        config.gpio_led_green,
        config.gpio_led_red,
        config.gpio_buzzer,
    )

    # NFC
    nfc = create_nfc_device(config.nfc_device, config.debounce_seconds)

    async def cb(chip, raw_data):
        await handle_tag(gpio, chip, raw_data)

    await nfc.start_polling(cb)

    # HTTP server
    app = create_app(nfc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.http_port)
    await site.start()
    logger.info(f"HTTP běží na http://0.0.0.0:{config.http_port}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()

    logger.info("Shutting down...")
    await nfc.stop()
    gpio.cleanup()
    await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
