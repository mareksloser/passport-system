"""
NFC abstrakce nad nfcpy / PN532.

Tři operace:
  - read_passport()        → PassportChip nebo None (žádný čip)
  - write_passport(chip)   → True/False
  - poll_loop(on_tag)      → opakovaně čte a callbackuje

Tři implementace:
  - MockNfcDevice          → emuluje paměť in-memory pro vývoj
  - Pn532NfcDevice         → reálná HW přes nfcpy
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional

from passport_chip import CHIP_SIZE, PassportChip, ChipDataError, is_blank_chip

logger = logging.getLogger(__name__)

# Callback dostává buď validní PassportChip, nebo None pokud čip není inicializovaný
# (přilepený čistý NTAG bez našich dat)
OnTagCallback = Callable[[Optional[PassportChip], bytes], Awaitable[None]]


class NfcDevice(ABC):
    @abstractmethod
    async def start_polling(self, on_tag: OnTagCallback) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    async def write_data(self, data: bytes) -> bool:
        """Zapíše data na čip, který je právě přiložen. True/False."""
        ...

    @abstractmethod
    async def read_data(self) -> Optional[bytes]:
        """Přečte data z čipu, který je právě přiložen, nebo None."""
        ...


# ==========================================================================
# MOCK
# ==========================================================================

class MockNfcDevice(NfcDevice):
    """
    Mock implementace pro vývoj bez HW.
    Emuluje "virtuální čip" - vnitřně si drží buffer 64 B.
    
    Použití v testech:
      device = MockNfcDevice()
      await device.simulate_tag(some_64_byte_data)  # přilož čip
      data = await device.read_data()
    """

    def __init__(self) -> None:
        self._current_chip: Optional[bytearray] = None
        self._on_tag: Optional[OnTagCallback] = None
        self._polling = False
        self._debounce_seconds = 1.0
        self._last_tag_time: float = 0
        self._last_tag_hash: Optional[int] = None

    async def start_polling(self, on_tag: OnTagCallback) -> None:
        self._on_tag = on_tag
        self._polling = True
        logger.info("MockNfcDevice: polling started")

    async def stop(self) -> None:
        self._polling = False

    async def simulate_tag(self, data: bytes) -> None:
        """Externí 'přiložení' čipu - zavolá callback."""
        if not self._polling or not self._on_tag:
            return

        # Debounce
        now = time.monotonic()
        data_hash = hash(bytes(data))
        if data_hash == self._last_tag_hash and (now - self._last_tag_time) < self._debounce_seconds:
            logger.debug("Mock: debounced")
            return
        self._last_tag_hash = data_hash
        self._last_tag_time = now

        self._current_chip = bytearray(data)

        # Pokus se data deserializovat
        chip: Optional[PassportChip] = None
        if not is_blank_chip(data):
            try:
                chip = PassportChip.from_bytes(bytes(data))
            except ChipDataError as e:
                logger.warning(f"Mock: data nejsou validní passport: {e}")

        await self._on_tag(chip, bytes(data))

    async def simulate_blank_tag(self) -> None:
        """Přiložen prázdný NTAG."""
        await self.simulate_tag(b"\x00" * CHIP_SIZE)

    async def write_data(self, data: bytes) -> bool:
        if len(data) != CHIP_SIZE:
            raise ValueError(f"data must be {CHIP_SIZE} B")
        self._current_chip = bytearray(data)
        logger.info(f"Mock: zapsáno {len(data)} B na čip")
        return True

    async def read_data(self) -> Optional[bytes]:
        if self._current_chip is None:
            return None
        return bytes(self._current_chip)


# ==========================================================================
# PN532 přes nfcpy
# ==========================================================================

class Pn532NfcDevice(NfcDevice):
    """
    Reálný PN532 přes nfcpy.

    Device string formát (viz nfcpy docs):
      - 'usb' nebo 'usb:VID:PID' pro USB
      - 'tty:USB0:pn532' pro UART na /dev/ttyUSB0
      - 'tty:AMA0:pn532' pro UART na /dev/ttyAMA0
      - 'i2c:/dev/i2c-1:pn532' pro I2C
    """

    def __init__(self, device_string: str, debounce_seconds: float = 1.5) -> None:
        self.device_string = device_string
        self.debounce_seconds = debounce_seconds
        self._on_tag: Optional[OnTagCallback] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._stop_requested = False
        self._last_uid_hash: Optional[int] = None
        self._last_uid_time: float = 0
        self._current_tag = None  # aktuálně přiložený nfcpy tag (pro write_data)
        self._tag_lock = asyncio.Lock()

    async def start_polling(self, on_tag: OnTagCallback) -> None:
        self._on_tag = on_tag
        self._loop = asyncio.get_running_loop()
        self._stop_requested = False
        self._poll_task = asyncio.create_task(
            asyncio.to_thread(self._poll_loop_blocking)
        )
        logger.info(f"Pn532NfcDevice: polling started on {self.device_string}")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._poll_task:
            self._poll_task.cancel()

    def _poll_loop_blocking(self) -> None:
        try:
            import nfc  # type: ignore
        except ImportError:
            logger.error("nfcpy není dostupné. Nainstaluj: pip install nfcpy")
            return

        try:
            with nfc.ContactlessFrontend(self.device_string) as clf:
                logger.info(f"NFC otevřeno: {clf}")
                while not self._stop_requested:
                    try:
                        clf.connect(
                            rdwr={
                                "on-connect": self._on_tag_blocking,
                                "iterations": 1,
                                "interval": 0.1,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"NFC iter chyba: {e}")
                        time.sleep(0.3)
        except Exception as e:
            logger.error(f"NFC zařízení nelze otevřít: {e}")

    def _on_tag_blocking(self, tag) -> bool:
        """Sync callback z nfcpy."""
        try:
            uid_hash = hash(bytes(tag.identifier))
            now = time.monotonic()

            # Debounce
            if (
                uid_hash == self._last_uid_hash
                and (now - self._last_uid_time) < self.debounce_seconds
            ):
                return False

            self._last_uid_hash = uid_hash
            self._last_uid_time = now

            # Čti uživatelskou paměť NTAG213 (stránky 4..19 = 64 B)
            data = self._read_ntag213(tag)

            # Drž tag pro případný write
            self._current_tag = tag

            # Pokus se deserializovat
            chip: Optional[PassportChip] = None
            if data and not is_blank_chip(data):
                try:
                    chip = PassportChip.from_bytes(data)
                except ChipDataError as e:
                    logger.warning(f"Čip nemá validní passport data: {e}")

            # Callback v event loopu
            if self._on_tag and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._on_tag(chip, data or b""), self._loop
                )

        except Exception as e:
            logger.error(f"on_tag chyba: {e}")
        return False  # neblokuj tag pro další čtení

    @staticmethod
    def _read_ntag213(tag) -> Optional[bytes]:
        """Přečte 64 B z NTAG213 (stránky 4..19)."""
        try:
            # nfcpy: tag.read(page) vrací 16 bytes (4 stránky)
            buf = bytearray()
            for page in range(4, 20, 4):
                chunk = tag.read(page)
                buf.extend(chunk[:16])
            return bytes(buf[:CHIP_SIZE])
        except Exception as e:
            logger.error(f"NTAG read chyba: {e}")
            return None

    async def write_data(self, data: bytes) -> bool:
        """Zapíše data na aktuálně přiložený čip."""
        if len(data) != CHIP_SIZE:
            raise ValueError(f"data must be {CHIP_SIZE} B")

        if self._current_tag is None:
            logger.error("Žádný čip není přiložen pro zápis")
            return False

        # nfcpy write je blocking - pusť do threadu
        success = await asyncio.to_thread(
            self._write_ntag213_blocking, self._current_tag, data
        )
        return success

    @staticmethod
    def _write_ntag213_blocking(tag, data: bytes) -> bool:
        """Zapíše 64 B (16 stránek) na NTAG213 od stránky 4."""
        try:
            # NTAG213: 4 B per page, zápis po jedné stránce
            for i in range(0, CHIP_SIZE, 4):
                page = 4 + (i // 4)
                page_data = data[i:i + 4]
                tag.write(page, page_data)
            return True
        except Exception as e:
            logger.error(f"NTAG write chyba: {e}")
            return False

    async def read_data(self) -> Optional[bytes]:
        if self._current_tag is None:
            return None
        return await asyncio.to_thread(
            self._read_ntag213, self._current_tag
        )


# ==========================================================================
# Factory
# ==========================================================================

def create_nfc_device(
    device_string: str,
    debounce_seconds: float = 1.5,
) -> NfcDevice:
    if device_string == "mock":
        return MockNfcDevice()
    return Pn532NfcDevice(device_string, debounce_seconds)
