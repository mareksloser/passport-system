"""E2E test registrační stanice (bez fotky)."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

TEMP = tempfile.mkdtemp(prefix="reg_e2e_")
os.environ["PASSPORT_NFC_DEVICE"] = "mock"
os.environ["PASSPORT_HTTP_PORT"] = "18092"
os.environ["PASSPORT_LOG_DIR"] = TEMP

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.daemon import create_app, on_tag, state  # noqa: E402
from nfc_device import MockNfcDevice  # noqa: E402
from passport_chip import PassportChip  # noqa: E402
from aiohttp import web  # noqa: E402

PORT = 18092


async def run():
    print("=" * 60)
    print("E2E test registrační stanice (bez fotky)")
    print("=" * 60)

    nfc = MockNfcDevice()

    async def cb(chip, raw_data):
        await on_tag(nfc, chip, raw_data)

    await nfc.start_polling(cb)
    app = create_app(nfc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}") as client:

        # === Health ===
        r = await client.get("/health")
        assert r.status_code == 200
        print(f"✓ Health: {r.json()['status']}")

        # === Frontend assets ===
        for url in ["/", "/css/style.css", "/js/app.js", "/assets/logo.svg"]:
            r = await client.get(url)
            assert r.status_code == 200, f"{url}: {r.status_code}"
        print("✓ Frontend assets")

        # === 1. Registrace s prázdným čipem ===
        print("\n--- Test 1: Registrace s prázdným pasem ---")
        r = await client.get("/mock?action=blank")
        assert r.status_code == 200
        await asyncio.sleep(0.2)
        assert state.current_tag["type"] == "blank"
        print("  ✓ Mock blank tag detekován")

        r = await client.post(
            "/api/register",
            json={"first_name": "Pavel", "gender": "M", "birth_year": 2014},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["passport"]["first_name"] == "Pavel"
        print(f"  ✓ Registrace OK: {data['passport']}")

        chip_data = await nfc.read_data()
        chip = PassportChip.from_bytes(chip_data)
        assert chip.first_name == "Pavel"
        assert chip.gender == "M"
        assert chip.birth_year == 2014
        print(f"  ✓ Čip přečten: {chip.first_name} {chip.gender} {chip.birth_year}")

        # === 2. Re-registrace bez confirm vrátí 409 ===
        print("\n--- Test 2: Re-registrace bez potvrzení ---")
        assert state.current_tag["type"] == "registered"
        r = await client.post(
            "/api/register",
            json={"first_name": "Eliška", "gender": "F", "birth_year": 2015},
        )
        assert r.status_code == 409
        d = r.json()
        assert d["need_confirmation"] is True
        assert d["existing"]["first_name"] == "Pavel"
        print(f"  ✓ 409 Conflict s informací o existujícím pasu")

        # === 3. Re-registrace s force_overwrite ===
        print("\n--- Test 3: Re-registrace s overwrite ---")
        r = await client.post(
            "/api/register",
            json={
                "first_name": "Eliška",
                "gender": "F",
                "birth_year": 2015,
                "force_overwrite": True,
            },
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["passport"]["first_name"] == "Eliška"
        print(f"  ✓ Přepis úspěšný: {d['passport']}")

        chip_data = await nfc.read_data()
        chip = PassportChip.from_bytes(chip_data)
        assert chip.first_name == "Eliška"
        assert chip.unique_countries_visited == 0
        assert chip.total_scans == 0
        print(f"  ✓ Historie vynulována")

        # === 4. Validace ===
        print("\n--- Test 4: Validace ---")
        r = await client.get("/mock?action=blank")
        await asyncio.sleep(0.2)

        # Dlouhé jméno
        r = await client.post(
            "/api/register",
            json={"first_name": "Aleksandrovičová", "gender": "F", "birth_year": 2014},
        )
        assert r.status_code == 400
        print(f"  ✓ Dlouhé jméno odmítnuto")

        # Špatný rok
        r = await client.post(
            "/api/register",
            json={"first_name": "Pavel", "gender": "M", "birth_year": 1950},
        )
        assert r.status_code == 400
        print(f"  ✓ Špatný rok odmítnut")

        # Špatné pohlaví
        r = await client.post(
            "/api/register",
            json={"first_name": "Pavel", "gender": "X", "birth_year": 2014},
        )
        assert r.status_code == 400
        print(f"  ✓ Špatné pohlaví odmítnuto")

        # === 5. Bez čipu ===
        print("\n--- Test 5: Bez čipu ---")
        r = await client.get("/mock?action=remove")
        await asyncio.sleep(0.2)
        r = await client.post(
            "/api/register",
            json={"first_name": "Pavel", "gender": "M", "birth_year": 2014},
        )
        assert r.status_code == 400
        print(f"  ✓ Bez čipu odmítnuto")

        # === 6. Cizí (neplatný) čip ===
        print("\n--- Test 6: Cizí čip ---")
        r = await client.get("/mock?action=invalid")
        await asyncio.sleep(0.2)
        assert state.current_tag["type"] == "invalid"
        r = await client.post(
            "/api/register",
            json={"first_name": "Pavel", "gender": "M", "birth_year": 2014},
        )
        assert r.status_code == 400
        print(f"  ✓ Cizí čip odmítnut")

        # === 7. Audit log ===
        print("\n--- Test 7: Audit log ---")
        log_file = Path(TEMP) / "registrations.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 2
        print(f"  ✓ Log obsahuje {len(lines)} záznamů")

    await runner.cleanup()
    await nfc.stop()
    print("\n" + "=" * 60)
    print("✅ E2E test registrační stanice - vše prošlo")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())
