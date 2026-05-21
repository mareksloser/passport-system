"""Konfigurace pokladny."""
import os
from pathlib import Path


def _load_conf(path: Path) -> dict:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


class Config:
    def __init__(self) -> None:
        conf = {}
        for p in [Path("/boot/station.conf"), Path("/etc/passport/station.conf")]:
            conf.update(_load_conf(p))

        def get(key: str, default: str = "") -> str:
            return os.environ.get(f"PASSPORT_{key}", conf.get(key, default))

        # NFC
        self.nfc_device: str = get("NFC_DEVICE", "mock")
        self.debounce_seconds: float = float(get("DEBOUNCE_SECONDS", "2.0"))

        # HTTP server
        self.http_port: int = int(get("HTTP_PORT", "8090"))

        # GPIO LED (volitelné)
        # Pokud nejsou pinout nastaveny, GPIO se nepoužívá
        self.gpio_enabled: bool = get("GPIO_ENABLED", "false").lower() in ("true", "1", "yes")
        self.gpio_led_green: int = int(get("GPIO_LED_GREEN", "17"))
        self.gpio_led_red: int = int(get("GPIO_LED_RED", "27"))
        self.gpio_buzzer: int = int(get("GPIO_BUZZER", "22"))

        # Display / behavior
        self.show_result_seconds: float = float(get("SHOW_RESULT_SECONDS", "5"))
        self.checkpoint_label: str = get("CHECKPOINT_LABEL", "Pokladna")

        # Cesty
        self.base_dir = Path(__file__).resolve().parent.parent
        self.frontend_dir = self.base_dir / "frontend"
        self.log_dir = Path(get("LOG_DIR", "/var/log/passport"))
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.log_dir = Path("/tmp/passport-logs")
            self.log_dir.mkdir(parents=True, exist_ok=True)


config = Config()
