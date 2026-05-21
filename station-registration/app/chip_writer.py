"""
Zápis na čip s ověřením.

Strategie:
1. Připrav nový PassportChip s daty
2. Zapiš na čip
3. Re-read - přečti zpět
4. Porovnej - musí být byte-for-byte stejné
5. Pokud sedí → OK, jinak → znova (max 3x)
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# Přidat shared do path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from nfc_device import NfcDevice  # noqa: E402
from passport_chip import (  # noqa: E402
    CHIP_SIZE,
    ChipDataError,
    PassportChip,
)

logger = logging.getLogger(__name__)

MAX_WRITE_RETRIES = 3


class ChipWriteError(Exception):
    """Zápis na čip selhal i po opakování."""


async def write_passport_safe(
    nfc: NfcDevice,
    chip: PassportChip,
) -> PassportChip:
    """
    Bezpečně zapíše PassportChip na aktuálně přiložený čip.

    Postup:
      1. Serializuje data → 64 B
      2. Pošle write_data() na NFC
      3. Re-read - ověří, že data jsou tam správně
      4. Pokud nesedí → 2 další pokusy

    Vrací re-read PassportChip pokud uspěje.
    Vyhodí ChipWriteError pokud i po opakování selže.
    """
    expected_bytes = chip.to_bytes()
    assert len(expected_bytes) == CHIP_SIZE

    last_error: Optional[str] = None

    for attempt in range(1, MAX_WRITE_RETRIES + 1):
        logger.info(f"Zápis na čip (pokus {attempt}/{MAX_WRITE_RETRIES})")

        # 1. Zápis
        success = await nfc.write_data(expected_bytes)
        if not success:
            last_error = "nfc.write_data() vrátilo False"
            logger.warning(f"Pokus {attempt}: {last_error}")
            await asyncio.sleep(0.3)
            continue

        # 2. Re-read pro ověření
        readback = await nfc.read_data()
        if readback is None:
            last_error = "Re-read selhal (čip pravděpodobně odtažen)"
            logger.warning(f"Pokus {attempt}: {last_error}")
            await asyncio.sleep(0.3)
            continue

        # 3. Porovnání
        if readback[:CHIP_SIZE] != expected_bytes:
            last_error = (
                f"Re-read data nesedí.\n"
                f"  Očekáváno: {expected_bytes.hex()}\n"
                f"  Načteno:   {readback[:CHIP_SIZE].hex()}"
            )
            logger.warning(f"Pokus {attempt}: data nesedí")
            await asyncio.sleep(0.3)
            continue

        # 4. Ověř, že re-read se dá deserializovat
        try:
            verified_chip = PassportChip.from_bytes(readback[:CHIP_SIZE])
        except ChipDataError as e:
            last_error = f"Re-read data neprojdou deserializací: {e}"
            logger.warning(f"Pokus {attempt}: {last_error}")
            await asyncio.sleep(0.3)
            continue

        logger.info(f"✓ Zápis úspěšný a ověřený (pokus {attempt})")
        return verified_chip

    raise ChipWriteError(
        f"Zápis na čip selhal po {MAX_WRITE_RETRIES} pokusech. "
        f"Poslední chyba: {last_error}"
    )
