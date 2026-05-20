"""
E2E test stanice země - daemon + frontend + mock NFC.

Spustí daemon v jednom procesu, simuluje různé scénáře a kontroluje:
  - Frontend dostane správné SSE eventy
  - Čip se zapisuje zpět s aktualizovanými daty
  - Greeting věty jsou správné pro každý scénář
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

TEMP = tempfile.mkdtemp(prefix="station_country_e2e_")
os.environ["PASSPORT_COUNTRY_INDEX"] = "2"  # Japonsko
os.environ["PASSPORT_NFC_DEVICE"] = "mock"
os.environ["PASSPORT_KIOSK_PORT"] = "18091"
os.environ["PASSPORT_LOG_DIR"] = TEMP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from app.daemon import create_app, handle_tag, state  # noqa: E402
from passport_chip import PassportChip  # noqa: E402
from nfc_device import MockNfcDevice  # noqa: E402
from aiohttp import web  # noqa: E402

KIOSK_PORT = 18091


async def wait_until(predicate, timeout=5.0, interval=0.05):
    """Čekej, dokud predicate vrátí True nebo timeout."""
    elapsed = 0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


async def collect_sse_events(client, count, timeout=5.0):
    """Sbírá count eventů z SSE streamu."""
    events = []
    async with client.stream("GET", f"http://127.0.0.1:{KIOSK_PORT}/events", timeout=timeout) as r:
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                    if len(events) >= count:
                        return events
                except json.JSONDecodeError:
                    pass
    return events


async def run():
    print("=" * 60)
    print("E2E test stanice země (Japonsko, idx=2)")
    print("=" * 60)

    nfc = MockNfcDevice()

    async def on_tag(chip, raw_data):
        await handle_tag(nfc, chip, raw_data)

    await nfc.start_polling(on_tag)

    app = create_app(nfc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", KIOSK_PORT)
    await site.start()

    async with httpx.AsyncClient() as client:
        # === Health check ===
        r = await client.get(f"http://127.0.0.1:{KIOSK_PORT}/health")
        h = r.json()
        assert h["status"] == "ok"
        assert h["country_index"] == 2
        assert h["country_name"] == "Japonsko"
        print(f"✓ Health: {h['country_name']} (idx={h['country_index']})")

        # === Frontend HTML ===
        r = await client.get(f"http://127.0.0.1:{KIOSK_PORT}/")
        assert r.status_code == 200
        assert "Srdcem pro Ondráška" in r.text
        print("✓ Frontend HTML")

        # === Static assets ===
        r = await client.get(f"http://127.0.0.1:{KIOSK_PORT}/assets/logo.svg")
        assert r.status_code == 200
        r = await client.get(f"http://127.0.0.1:{KIOSK_PORT}/css/style.css")
        assert r.status_code == 200
        r = await client.get(f"http://127.0.0.1:{KIOSK_PORT}/js/app.js")
        assert r.status_code == 200
        print("✓ Static assets")

        # === Test 1: Prázdný čip ===
        print("\n--- Test 1: Prázdný (neregistrovaný) čip ---")
        await nfc.simulate_blank_tag()
        await asyncio.sleep(0.2)
        assert state.last_event["type"] == "error"
        assert "registr" in state.last_event["data"]["message"].lower()
        print(f"✓ Prázdný čip → error: {state.last_event['data']['message'][:60]}...")

        # === Test 2: Registrovaný čip, první návštěva (z registrace) ===
        print("\n--- Test 2: První návštěva z registrace ---")
        chip = PassportChip(first_name="Tomáš", gender="M", birth_year=2014)
        # Přes mock: GET /mock?name=Tomáš&gender=M&year=2014
        r = await client.get(
            f"http://127.0.0.1:{KIOSK_PORT}/mock?name=Tom%C3%A1%C5%A1&gender=M&year=2014"
        )
        result = r.json()
        await asyncio.sleep(0.2)
        assert state.last_event["type"] == "scan"
        ev = state.last_event["data"]
        assert "Ahoj Tomáš" in ev["greeting"]
        assert "v Japonsku" in ev["greeting"]
        assert "začal cestovat" in ev["greeting"]
        assert ev["fact"] is not None
        print(f"✓ Greeting: {ev['greeting']}")
        print(f"  Fakt: {ev['fact']}")
        # Po zápisu by měl mít chip last_country_idx=2, visits[2]=1
        assert result["after"]["last_country_idx"] == 2
        assert result["after"]["visits_to_this"] == 1
        print(f"  Čip aktualizován: last_country_idx={result['after']['last_country_idx']}, visits={result['after']['visits_to_this']}")

        # === Test 3: Druhá země - "Jak bylo v X?" ===
        print("\n--- Test 3: Příchod z jiné země ---")
        # Simuluj, že už byl ve Francii (idx 1)
        await asyncio.sleep(2.5)  # debounce
        r = await client.get(
            f"http://127.0.0.1:{KIOSK_PORT}/mock?name=Eli%C5%A1ka&gender=F&year=2014&visited=1"
        )
        await asyncio.sleep(0.2)
        ev = state.last_event["data"]
        assert "Ahoj Eliška" in ev["greeting"]
        assert "v Japonsku" in ev["greeting"]
        assert "Jak bylo ve Francii" in ev["greeting"]
        print(f"✓ {ev['greeting']}")

        # === Test 4: Opakovaná návštěva ===
        print("\n--- Test 4: Opakovaná návštěva ---")
        await asyncio.sleep(2.5)
        # Eliška už byla v Japonsku 1x (visited=2)
        r = await client.get(
            f"http://127.0.0.1:{KIOSK_PORT}/mock?name=Eli%C5%A1ka&gender=F&visited=2"
        )
        await asyncio.sleep(0.2)
        ev = state.last_event["data"]
        assert "Vítej zpět" in ev["greeting"]
        assert "v Japonsku" in ev["greeting"]
        assert "byla 2krát" in ev["greeting"]
        print(f"✓ {ev['greeting']}")

        # === Test 5: Dokončení - 11. unikátní zemí je Japonsko ===
        print("\n--- Test 5: Dokončení cesty ---")
        await asyncio.sleep(2.5)
        # Byl ve všech 10 jiných zemích, teď jde do Japonska (idx 2)
        visited = ",".join(str(i) for i in range(11) if i != 2)
        r = await client.get(
            f"http://127.0.0.1:{KIOSK_PORT}/mock?name=Pavel&gender=M&visited={visited}"
        )
        await asyncio.sleep(0.2)
        assert state.last_event["type"] == "completion"
        ev = state.last_event["data"]
        assert "Gratulujeme, Pavel" in ev["greeting"]
        assert "dokončil cestu kolem světa" in ev["greeting"]
        assert "Ondráška" in ev["greeting"]
        print(f"✓ {ev['greeting'][:120]}...")

        # === Test 6: Audit log existuje ===
        print("\n--- Test 6: Audit log ---")
        log_file = Path(TEMP) / "scans.jsonl"
        assert log_file.exists(), "Audit log neexistuje"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 4
        for line in lines:
            entry = json.loads(line)
            assert "ts" in entry
            assert entry["country_idx"] == 2
        print(f"✓ Audit log obsahuje {len(lines)} záznamů")

    await runner.cleanup()
    await nfc.stop()
    print("\n" + "=" * 60)
    print("✅ Stanice země - všechny testy prošly")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())
