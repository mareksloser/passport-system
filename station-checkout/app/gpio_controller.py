"""
GPIO ovládání LED a bzučáku.

Tři implementace:
  - RealGpio        - skutečné RPi.GPIO
  - MockGpio        - tisk do logu (pro vývoj na PC)
  - NoOpGpio        - nedělá nic (pokud je GPIO vypnuto v configu)
"""
import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class GpioController(ABC):
    @abstractmethod
    async def green_on(self, duration: float) -> None: ...
    @abstractmethod
    async def red_on(self, duration: float) -> None: ...
    @abstractmethod
    async def beep_ok(self) -> None: ...
    @abstractmethod
    async def beep_fail(self) -> None: ...
    @abstractmethod
    def cleanup(self) -> None: ...


class NoOpGpio(GpioController):
    """Nedělá nic - když GPIO není zapnuté."""
    async def green_on(self, duration: float) -> None: pass
    async def red_on(self, duration: float) -> None: pass
    async def beep_ok(self) -> None: pass
    async def beep_fail(self) -> None: pass
    def cleanup(self) -> None: pass


class MockGpio(GpioController):
    """Mock - jen tiskne do logu. Užitečné pro vývoj na PC."""

    async def green_on(self, duration: float) -> None:
        logger.info(f"🟢 [MOCK GPIO] LED ZELENÁ {duration}s")
        await asyncio.sleep(duration)
        logger.info("⚪ [MOCK GPIO] LED OFF")

    async def red_on(self, duration: float) -> None:
        logger.info(f"🔴 [MOCK GPIO] LED ČERVENÁ {duration}s")
        await asyncio.sleep(duration)
        logger.info("⚪ [MOCK GPIO] LED OFF")

    async def beep_ok(self) -> None:
        logger.info("🔔 [MOCK GPIO] Bzučák PÍP (krátké)")

    async def beep_fail(self) -> None:
        logger.info("🔔🔔🔔 [MOCK GPIO] Bzučák PÍP-PÍP-PÍP (dlouhé)")

    def cleanup(self) -> None:
        logger.info("[MOCK GPIO] cleanup")


class RealGpio(GpioController):
    """Skutečné RPi.GPIO."""

    def __init__(self, pin_green: int, pin_red: int, pin_buzzer: int) -> None:
        try:
            import RPi.GPIO as GPIO  # type: ignore
        except ImportError:
            raise RuntimeError(
                "RPi.GPIO není nainstalované. Nainstaluj: pip install RPi.GPIO"
            )
        self.GPIO = GPIO
        self.pin_green = pin_green
        self.pin_red = pin_red
        self.pin_buzzer = pin_buzzer

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin_green, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(pin_red, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(pin_buzzer, GPIO.OUT, initial=GPIO.LOW)
        logger.info(f"GPIO inicializováno: green={pin_green}, red={pin_red}, buzzer={pin_buzzer}")

    async def green_on(self, duration: float) -> None:
        self.GPIO.output(self.pin_green, self.GPIO.HIGH)
        try:
            await asyncio.sleep(duration)
        finally:
            self.GPIO.output(self.pin_green, self.GPIO.LOW)

    async def red_on(self, duration: float) -> None:
        self.GPIO.output(self.pin_red, self.GPIO.HIGH)
        try:
            await asyncio.sleep(duration)
        finally:
            self.GPIO.output(self.pin_red, self.GPIO.LOW)

    async def beep_ok(self) -> None:
        """Krátké pípnutí 200 ms."""
        self.GPIO.output(self.pin_buzzer, self.GPIO.HIGH)
        await asyncio.sleep(0.2)
        self.GPIO.output(self.pin_buzzer, self.GPIO.LOW)

    async def beep_fail(self) -> None:
        """3× krátké pípnutí - jasně rozlišitelné od OK."""
        for _ in range(3):
            self.GPIO.output(self.pin_buzzer, self.GPIO.HIGH)
            await asyncio.sleep(0.1)
            self.GPIO.output(self.pin_buzzer, self.GPIO.LOW)
            await asyncio.sleep(0.08)

    def cleanup(self) -> None:
        try:
            self.GPIO.output(self.pin_green, self.GPIO.LOW)
            self.GPIO.output(self.pin_red, self.GPIO.LOW)
            self.GPIO.output(self.pin_buzzer, self.GPIO.LOW)
            self.GPIO.cleanup()
        except Exception:
            pass


def create_gpio(enabled: bool, pin_green: int, pin_red: int, pin_buzzer: int) -> GpioController:
    """Factory - vrátí real GPIO nebo mock."""
    if not enabled:
        return NoOpGpio()
    try:
        return RealGpio(pin_green, pin_red, pin_buzzer)
    except RuntimeError as e:
        logger.warning(f"RPi.GPIO nedostupné, používám mock: {e}")
        return MockGpio()
