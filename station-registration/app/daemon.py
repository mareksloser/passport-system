"""
Daemon registrační stanice (bez fotky - tu vyřeší organizátor mimo systém).

Tok:
  1. Operátor otevře web UI na notebooku
  2. UI zobrazí stav "Čekám na čip" + formulář
  3. Operátor přiloží pas:
     - Pokud blank → UI nabídne formulář pro registraci
     - Pokud již zaregistrovaný → UI zobrazí existující data + možnost přepsat
  4. Operátor vyplní jméno/pohlaví/rok a klikne "Zaregistrovat"
  5. Server zapíše data na čip s ověřením
  6. UI gratuluje, vrací se do "čekám na čip" stavu
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

from app.config import config  # noqa: E402
from app.chip_writer import ChipWriteError, write_passport_safe  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("station-registration")


# ==========================================================================
# Sdílený stav
# ==========================================================================

class RegistrationState:
    def __init__(self) -> None:
        self.sse_clients: list[web.StreamResponse] = []
        # Aktuálně přiložený čip: None | {"type": "blank"|"invalid"|"registered", "chip": PassportChip|None}
        self.current_tag: Optional[dict] = None
        self.register_lock = asyncio.Lock()

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


state = RegistrationState()


# ==========================================================================
# NFC callback
# ==========================================================================

async def on_tag(nfc: NfcDevice, chip: Optional[PassportChip], raw_data: bytes) -> None:
    if chip is None:
        is_blank = is_blank_chip(raw_data)
        logger.info(f"Tag: {'blank' if is_blank else 'invalid'}")
        state.current_tag = {
            "type": "blank" if is_blank else "invalid",
            "chip": None,
        }
        await state.push("tag_present", {
            "type": "blank" if is_blank else "invalid",
            "message": (
                "Prázdný pas, připraven k registraci."
                if is_blank
                else "Tento čip nepatří k naší akci nebo má poškozená data."
            ),
        })
        return

    logger.info(f"Tag: registrovaný '{chip.first_name}'")
    state.current_tag = {"type": "registered", "chip": chip}
    await state.push("tag_present", {
        "type": "registered",
        "passport": {
            "first_name": chip.first_name,
            "gender": chip.gender,
            "birth_year": chip.birth_year,
            "unique_countries": chip.unique_countries_visited,
            "total_scans": chip.total_scans,
            "completed": chip.completed,
        },
    })


# ==========================================================================
# Audit log
# ==========================================================================

def log_registration(action: str, details: dict) -> None:
    log_file = config.log_dir / "registrations.jsonl"
    entry = {"ts": datetime.utcnow().isoformat(), "action": action, **details}
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Audit log chyba: {e}")


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

    init_payload = {"type": "init", "data": {"station_type": "registration"}}
    try:
        msg = f"data: {json.dumps(init_payload, ensure_ascii=False)}\n\n"
        await response.write(msg.encode("utf-8"))

        # Pošli také aktuální stav čipu (pokud je přiložen po refresh)
        if state.current_tag:
            tag_payload = {"type": "tag_present", "data": {"type": state.current_tag["type"]}}
            if state.current_tag["chip"]:
                c = state.current_tag["chip"]
                tag_payload["data"]["passport"] = {
                    "first_name": c.first_name,
                    "gender": c.gender,
                    "birth_year": c.birth_year,
                    "unique_countries": c.unique_countries_visited,
                    "total_scans": c.total_scans,
                    "completed": c.completed,
                }
            msg = f"data: {json.dumps(tag_payload, ensure_ascii=False)}\n\n"
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


async def register_handler(request: web.Request) -> web.Response:
    """
    Hlavní endpoint:
      POST /api/register
      {
        "first_name": "Pavel",
        "gender": "M",
        "birth_year": 2014,
        "force_overwrite": false
      }
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    first_name = payload.get("first_name", "").strip()
    gender = payload.get("gender", "M")
    try:
        birth_year = int(payload.get("birth_year", 0))
    except (TypeError, ValueError):
        return web.json_response({"error": "Rok narození musí být číslo."}, status=400)
    force_overwrite = bool(payload.get("force_overwrite", False))

    # Validace
    if not first_name:
        return web.json_response({"error": "Jméno je povinné."}, status=400)
    if len(first_name.encode("utf-8")) > 15:
        return web.json_response({
            "error": f"Jméno '{first_name}' je dlouhé (max 15 znaků v UTF-8). "
                     f"Použij kratší variantu."
        }, status=400)
    if gender not in ("M", "F"):
        return web.json_response({"error": "Pohlaví musí být M nebo F."}, status=400)
    if not 2005 <= birth_year <= 2025:
        return web.json_response({
            "error": f"Rok narození {birth_year} mimo rozsah 2005-2025."
        }, status=400)

    async with state.register_lock:
        if state.current_tag is None:
            return web.json_response({
                "error": "Žádný pas není přiložen. Polož pas na čtečku."
            }, status=400)

        tag_type = state.current_tag["type"]

        if tag_type == "invalid":
            return web.json_response({
                "error": "Tento čip nelze použít - data jsou poškozená "
                         "nebo nepatří k naší akci."
            }, status=400)

        if tag_type == "registered" and not force_overwrite:
            existing_chip = state.current_tag["chip"]
            return web.json_response({
                "error": "Tento pas je již zaregistrován.",
                "existing": {
                    "first_name": existing_chip.first_name,
                    "gender": existing_chip.gender,
                    "birth_year": existing_chip.birth_year,
                    "unique_countries": existing_chip.unique_countries_visited,
                },
                "need_confirmation": True,
            }, status=409)

        nfc: NfcDevice = request.app["nfc"]

        # Sestav nový PassportChip
        chip = PassportChip(
            first_name=first_name,
            gender=gender,
            birth_year=birth_year,
        )

        # Zápis na čip s ověřením
        try:
            written_chip = await write_passport_safe(nfc, chip)
        except ChipWriteError as e:
            log_registration("write_failed", {"name": first_name, "error": str(e)})
            return web.json_response({
                "error": f"Zápis na čip selhal: {e}. Zkus čip znovu přiložit."
            }, status=500)

        # Update stavu
        state.current_tag["chip"] = written_chip
        state.current_tag["type"] = "registered"

        log_registration("registered", {
            "name": first_name,
            "gender": gender,
            "birth_year": birth_year,
            "overwrite": force_overwrite,
        })

        await state.push("registered", {
            "passport": {
                "first_name": written_chip.first_name,
                "gender": written_chip.gender,
                "birth_year": written_chip.birth_year,
            },
        })

        return web.json_response({
            "status": "ok",
            "passport": {
                "first_name": written_chip.first_name,
                "gender": written_chip.gender,
                "birth_year": written_chip.birth_year,
            },
        })


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "nfc_device": config.nfc_device,
        "sse_clients": len(state.sse_clients),
        "tag_present": state.current_tag is not None,
        "tag_type": state.current_tag["type"] if state.current_tag else None,
    })


async def mock_handler(request: web.Request) -> web.Response:
    """Dev endpoint pro simulaci přiložení čipu."""
    nfc = request.app["nfc"]
    if not isinstance(nfc, MockNfcDevice):
        return web.json_response({"error": "Not in mock mode"}, status=400)

    action = request.query.get("action", "blank")
    if action == "blank":
        await nfc.simulate_blank_tag()
        return web.json_response({"status": "blank tag simulated"})
    elif action == "registered":
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
    elif action == "invalid":
        # Pošli "cizí" čip s neplatným magic byte
        bad_data = b"\xAA" * 64
        await nfc.simulate_tag(bad_data)
        return web.json_response({"status": "invalid tag simulated"})
    elif action == "remove":
        state.current_tag = None
        await state.push("tag_removed", {})
        return web.json_response({"status": "tag removed"})
    else:
        return web.json_response({"error": "Unknown action"}, status=400)


def create_app(nfc: NfcDevice) -> web.Application:
    app = web.Application(client_max_size=1024 * 1024)  # 1 MB stačí
    app["nfc"] = nfc
    app.router.add_get("/", index_handler)
    app.router.add_get("/events", events_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/mock", mock_handler)
    app.router.add_post("/api/register", register_handler)
    app.router.add_static("/css", config.frontend_dir / "css")
    app.router.add_static("/js", config.frontend_dir / "js")
    app.router.add_static("/assets", config.frontend_dir / "assets")
    return app


# ==========================================================================
# Main
# ==========================================================================

async def main() -> None:
    logger.info("== Stanice: Registrace ==")
    logger.info(f"NFC device: {config.nfc_device}")
    logger.info(f"HTTP port: {config.http_port}")

    nfc = create_nfc_device(config.nfc_device, config.debounce_seconds)

    async def cb(chip, raw_data):
        await on_tag(nfc, chip, raw_data)

    await nfc.start_polling(cb)

    app = create_app(nfc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.http_port)
    await site.start()
    logger.info(f"HTTP běží na http://0.0.0.0:{config.http_port}")
    logger.info("→ Otevři v prohlížeči na notebooku")

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
