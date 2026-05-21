"""E2E test pokladny."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

TEMP = tempfile.mkdtemp(prefix="checkout_e2e_")
os.environ["PASSPORT_NFC_DEVICE"] = "mock"
os.environ["PASSPORT_HTTP_PORT"] = "18093"
os.environ["PASSPORT_LOG_DIR"] = TEMP
os.environ["PASSPORT_CHECKPOINT_LABEL"] = "Test Pokladna 1"
os.environ["PASSPORT_GPIO_ENABLED"] = "false"
os.environ["PASSPORT_SHOW_RESULT_SECONDS"] = "0.5"  # rychlejší test

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.daemon import create_app, handle_tag, state  # noqa: E402
from app.gpio_controller import NoOpGpio  # noqa: E402
from nfc_device import MockNfcDevice  # noqa: E402
from passport_chip import PassportChip  # noqa: E402
from aiohttp import web  # noqa: E402

PORT = 18093


async def run():
    print("=" * 60)
    print("E2E test pokladny")
    print("=" * 60)

    nfc = MockNfcDevice()
    gpio = NoOpGpio()

    async def cb(chip, raw_data):
        await handle_tag(gpio, chip, raw_data)

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
        h = r.json()
        assert h["status"] == "ok"
        assert h["checkpoint"] == "Test Pokladna 1"
        assert h["gpio_enabled"] is False
        print(f"✓ Health: {h['checkpoint']}")

        # === Frontend assets ===
        for url in ["/", "/css/style.css", "/js/app.js", "/assets/logo.svg"]:
            r = await client.get(url)
            assert r.status_code == 200, f"{url}: {r.status_code}"
        print("✓ Frontend assets")

        # === 1. Validní pas - ACCEPT ===
        print("\n--- Test 1: Validní pas (ACCEPT) ---")
        r = await client.get("/mock?action=registered&name=Pavel&gender=M&year=2014&visited=0,1,2")
        assert r.status_code == 200
        await asyncio.sleep(0.3)

        # Server state push
        events = [json.loads(line.split("data: ", 1)[1])
                  for line in [str(state.__dict__)] if False]  # dummy

        # Po posledním pushu by mělo být accept
        # Simulujeme čtení přes přímé volání API
        # (státní stav neukládáme; ověřujeme přes log)
        log_file = Path(TEMP) / "checkouts.jsonl"
        await asyncio.sleep(0.1)
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        last = json.loads(lines[-1])
        assert last["action"] == "accept"
        assert last["name"] == "Pavel"
        assert last["unique_countries"] == 3
        assert last["completed"] is False
        print(f"✓ Accept: {last['name']} ({last['unique_countries']}/11)")

        # === 2. Dokončený pas ===
        print("\n--- Test 2: Dokončený pas ---")
        await asyncio.sleep(2.5)  # debounce
        r = await client.get("/mock?action=complete&name=Žofie&gender=F")
        await asyncio.sleep(0.3)
        lines = log_file.read_text().strip().split("\n")
        last = json.loads(lines[-1])
        assert last["action"] == "accept"
        assert last["name"] == "Žofie"
        assert last["completed"] is True
        assert last["unique_countries"] == 11
        print(f"✓ Completed: {last['name']} - 🎉 dokončila cestu")

        # === 3. Blank čip - DENY ===
        print("\n--- Test 3: Prázdný čip (DENY) ---")
        await asyncio.sleep(2.5)
        r = await client.get("/mock?action=blank")
        await asyncio.sleep(0.3)
        lines = log_file.read_text().strip().split("\n")
        last = json.loads(lines[-1])
        assert last["action"] == "deny"
        assert last["reason"] == "blank"
        print(f"✓ Deny blank: reason={last['reason']}")

        # === 4. Cizí čip - DENY ===
        print("\n--- Test 4: Cizí čip (DENY) ---")
        await asyncio.sleep(2.5)
        r = await client.get("/mock?action=invalid")
        await asyncio.sleep(0.3)
        lines = log_file.read_text().strip().split("\n")
        last = json.loads(lines[-1])
        assert last["action"] == "deny"
        assert last["reason"] == "invalid"
        print(f"✓ Deny invalid: reason={last['reason']}")

        # === 5. SSE eventy ===
        print("\n--- Test 5: SSE události ---")
        await asyncio.sleep(2.5)
        events_received = []

        async def listen():
            async with client.stream("GET", "/events", timeout=5.0) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            events_received.append(json.loads(line[6:]))
                            if len(events_received) >= 2:
                                break
                        except json.JSONDecodeError:
                            pass

        listen_task = asyncio.create_task(listen())
        await asyncio.sleep(0.3)
        await client.get("/mock?action=registered&name=Test&gender=M&year=2014")

        try:
            await asyncio.wait_for(listen_task, timeout=3.0)
        except asyncio.TimeoutError:
            pass

        types = [e["type"] for e in events_received]
        assert "init" in types
        assert "accept" in types
        print(f"✓ SSE eventy: {types}")

        # === 6. Audit log ===
        print("\n--- Test 6: Audit log ---")
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 4
        for line in lines:
            entry = json.loads(line)
            assert "ts" in entry
            assert "action" in entry
            assert entry["checkpoint"] == "Test Pokladna 1"
        print(f"✓ Audit log {len(lines)} záznamů s checkpoint labelem")

    await runner.cleanup()
    await nfc.stop()
    gpio.cleanup()
    print("\n" + "=" * 60)
    print("✅ E2E test pokladny - vše prošlo")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())
